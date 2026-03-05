from __future__ import annotations

import asyncio
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Awaitable, Callable

from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech

from app.config import Settings
from app.models import StreamEvent, StreamStartPayload
from app.services.gcp_helpers import (
    build_recognizer_name,
    build_streaming_recognition_config,
    choose_speech_model,
    normalize_translate_language,
)
from app.services.translation import TranslationService

EventSender = Callable[[dict], Awaitable[None]]


@dataclass(slots=True)
class _BufferedChunk:
    data: bytes
    duration_ms: int


class RealtimeTranscriptionSession:
    def __init__(
        self,
        *,
        settings: Settings,
        payload: StreamStartPayload,
        event_loop: asyncio.AbstractEventLoop,
        sender: EventSender,
    ) -> None:
        self._settings = settings
        self._payload = payload
        self._loop = event_loop
        self._sender = sender
        self._speech_client = speech_v2.SpeechClient()
        self._translator = TranslationService(
            payload.project_id or settings.google_cloud_project or "",
            settings.translation_location,
        )
        self._audio_queue: queue.Queue[bytes | None] = queue.Queue(maxsize=256)
        self._recent_chunks: deque[_BufferedChunk] = deque()
        self._recent_ms = 0
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._stop_event = threading.Event()
        self._last_final_signature: tuple[str, int] | None = None
        self._last_interim_text = ""
        self._last_interim_translation_at = 0.0
        self._project_id = payload.project_id or settings.google_cloud_project or ""
        if not self._project_id:
            raise ValueError("Missing Google Cloud project id.")

    def start(self) -> None:
        self._thread.start()

    def push_audio(self, chunk: bytes) -> None:
        if not chunk or self._stop_event.is_set():
            return
        duration_ms = int(len(chunk) / 2 / self._payload.sample_rate_hz * 1000)
        buffered = _BufferedChunk(data=chunk, duration_ms=max(duration_ms, 1))
        self._recent_chunks.append(buffered)
        self._recent_ms += buffered.duration_ms
        while self._recent_ms > 1500 and self._recent_chunks:
            removed = self._recent_chunks.popleft()
            self._recent_ms -= removed.duration_ms

        try:
            self._audio_queue.put_nowait(chunk)
        except queue.Full:
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                pass
            self._audio_queue.put_nowait(chunk)

    def close(self) -> None:
        self._stop_event.set()
        try:
            self._audio_queue.put_nowait(None)
        except queue.Full:
            pass
        self._thread.join(timeout=3)

    def _worker(self) -> None:
        self._send_status("已连接到后端，准备向 GCP 发起流式识别。")
        replay_chunks: list[bytes] = []
        while not self._stop_event.is_set():
            try:
                replay_chunks = self._run_single_stream(replay_chunks)
            except Exception as exc:  # noqa: BLE001
                self._send_event(
                    StreamEvent(type="error", message=f"实时识别失败: {exc}").model_dump()
                )
                return

    def _run_single_stream(self, replay_chunks: list[bytes]) -> list[bytes]:
        recognizer = build_recognizer_name(
            self._project_id,
            self._payload.speech_location or self._settings.speech_location,
            self._payload.recognizer_id or self._settings.recognizer_id,
        )
        model = choose_speech_model(
            streaming=True,
            auto_detect=self._payload.source_mode == "auto",
            location=self._payload.speech_location or self._settings.speech_location,
        )
        config = build_streaming_recognition_config(
            language_codes=self._payload.source_language_codes,
            model=model,
            sample_rate_hz=self._payload.sample_rate_hz,
            channel_count=self._payload.channel_count,
            interim_results=True,
        )
        deadline = time.monotonic() + (self._settings.streaming_restart_ms / 1000)

        def request_iter():
            yield cloud_speech.StreamingRecognizeRequest(
                recognizer=recognizer,
                streaming_config=config,
            )
            for chunk in replay_chunks:
                yield cloud_speech.StreamingRecognizeRequest(audio=chunk)
            while not self._stop_event.is_set():
                if time.monotonic() >= deadline:
                    return
                try:
                    chunk = self._audio_queue.get(timeout=0.25)
                except queue.Empty:
                    continue
                if chunk is None:
                    return
                yield cloud_speech.StreamingRecognizeRequest(audio=chunk)

        for response in self._speech_client.streaming_recognize(requests=request_iter()):
            self._handle_response(response)
            if self._stop_event.is_set():
                break

        return [item.data for item in self._recent_chunks]

    def _handle_response(self, response: cloud_speech.StreamingRecognizeResponse) -> None:
        for result in response.results:
            if not result.alternatives:
                continue
            transcript = result.alternatives[0].transcript.strip()
            if not transcript:
                continue
            language_code = result.language_code or (
                self._payload.source_language if self._payload.source_mode == "manual" else None
            )
            end_offset = _duration_to_seconds(result.result_end_offset)
            if result.is_final:
                signature = (transcript, int(end_offset * 1000))
                if signature == self._last_final_signature:
                    continue
                self._last_final_signature = signature
                self._last_interim_text = ""
                translation = self._translator.translate(
                    transcript,
                    target_language=normalize_translate_language(self._payload.target_language)
                    or "zh-CN",
                    source_language=normalize_translate_language(language_code),
                )
                self._send_event(
                    StreamEvent(
                        type="transcript",
                        transcript=transcript,
                        translation=translation,
                        is_final=True,
                        language_code=language_code,
                        end_offset=end_offset,
                    ).model_dump()
                )
            else:
                if transcript == self._last_interim_text:
                    continue
                self._last_interim_text = transcript
                translation = ""
                should_translate = (
                    self._payload.translate_interim
                    and self._settings.translate_interim_results
                    and len(transcript) >= self._settings.interim_translation_min_chars
                    and time.monotonic() - self._last_interim_translation_at
                    >= self._settings.interim_translation_min_interval_ms / 1000
                )
                if should_translate:
                    translation = self._translator.translate(
                        transcript,
                        target_language=normalize_translate_language(self._payload.target_language)
                        or "zh-CN",
                        source_language=normalize_translate_language(language_code),
                    )
                    self._last_interim_translation_at = time.monotonic()
                self._send_event(
                    StreamEvent(
                        type="transcript",
                        transcript=transcript,
                        translation=translation,
                        is_final=False,
                        language_code=language_code,
                        end_offset=end_offset,
                    ).model_dump()
                )

    def _send_status(self, message: str) -> None:
        self._send_event(StreamEvent(type="status", message=message).model_dump())

    def _send_event(self, payload: dict) -> None:
        future = asyncio.run_coroutine_threadsafe(self._sender(payload), self._loop)
        future.result(timeout=30)


def _duration_to_seconds(duration) -> float:
    return float(duration.seconds) + (float(duration.nanos) / 1_000_000_000)
