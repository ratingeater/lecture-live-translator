from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from tempfile import NamedTemporaryFile

from google.cloud import speech_v2
from google.cloud.speech_v2.types import cloud_speech

from app.config import Settings
from app.models import BatchTranscribeResponse
from app.services.gcp_helpers import (
    build_batch_recognition_config,
    build_recognizer_name,
    choose_speech_model,
    normalize_translate_language,
)
from app.services.storage import StorageService
from app.services.subtitles import SubtitleSegment, save_outputs
from app.services.translation import TranslationService


class BatchTranscribeService:
    def __init__(self, settings: Settings, project_id: str) -> None:
        self._settings = settings
        self._project_id = project_id
        self._speech_client = speech_v2.SpeechClient()
        self._storage = StorageService(project_id)
        self._translator = TranslationService(project_id, settings.translation_location)

    def transcribe_file(
        self,
        *,
        input_path: Path,
        speech_location: str,
        source_mode: str,
        source_language: str,
        target_language: str,
    ) -> BatchTranscribeResponse:
        speech_location = speech_location or self._settings.speech_location
        target_language = normalize_translate_language(target_language) or "zh-CN"
        audio_path = self._convert_to_flac(input_path)
        bucket_name = self._settings.upload_bucket or f"{self._project_id}-lecture-live-translator"
        bucket_location = self._bucket_location_for_speech(speech_location)
        self._storage.ensure_bucket(bucket_name, location=bucket_location)

        timestamp = int(time.time())
        blob_name = f"uploads/{timestamp}-{audio_path.name}"
        gcs_uri = self._storage.upload_file(
            bucket_name=bucket_name,
            local_path=audio_path,
            blob_name=blob_name,
        )

        auto_detect = source_mode == "auto"
        language_codes = (
            self._settings.auto_detect_languages if auto_detect else [source_language]
        )
        config = build_batch_recognition_config(
            language_codes=language_codes,
            model=choose_speech_model(
                streaming=False,
                auto_detect=auto_detect,
                location=speech_location,
            ),
        )
        request = cloud_speech.BatchRecognizeRequest(
            recognizer=build_recognizer_name(
                self._project_id,
                speech_location,
                self._settings.recognizer_id,
            ),
            config=config,
            files=[cloud_speech.BatchRecognizeFileMetadata(uri=gcs_uri)],
            recognition_output_config=cloud_speech.RecognitionOutputConfig(
                inline_response_config=cloud_speech.InlineOutputConfig(),
                output_format_config=cloud_speech.OutputFormatConfig(
                    native=cloud_speech.NativeOutputFileFormatConfig(),
                    srt=cloud_speech.SrtOutputFileFormatConfig(),
                ),
            ),
        )

        try:
            operation = self._speech_client.batch_recognize(request=request)
            response = operation.result(timeout=60 * 60)
            file_result = next(iter(response.results.values()))
            inline_result = file_result.inline_result
            native_transcript = inline_result.transcript
            segments = self._segments_from_results(
                native_transcript.results,
                target_language=target_language,
            )
            stem = f"{timestamp}-{input_path.stem}"
            output_dir = self._settings.temp_dir / "outputs"
            srt_path, transcript_path, translation_path = save_outputs(output_dir, stem, segments)
            transcript_text = transcript_path.read_text(encoding="utf-8")
            translation_text = translation_path.read_text(encoding="utf-8")
            return BatchTranscribeResponse(
                source_language=segments[0].source_language if segments else None,
                target_language=target_language,
                transcript_text=transcript_text,
                translation_text=translation_text,
                srt_content=srt_path.read_text(encoding="utf-8"),
                srt_path=str(srt_path),
                transcript_path=str(transcript_path),
            )
        finally:
            self._storage.delete_blob(bucket_name, blob_name)
            if audio_path.exists():
                audio_path.unlink(missing_ok=True)

    def _convert_to_flac(self, input_path: Path) -> Path:
        with NamedTemporaryFile(delete=False, suffix=".flac", dir=self._settings.temp_dir) as handle:
            output_path = Path(handle.name)
        command = [
            self._settings.ffmpeg_binary,
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(self._settings.audio_sample_rate_hz),
            "-sample_fmt",
            "s16",
            str(output_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode("utf-8", errors="ignore")
            raise RuntimeError(f"ffmpeg 转码失败: {stderr}") from exc
        return output_path

    def _segments_from_results(
        self,
        results: list[cloud_speech.SpeechRecognitionResult],
        *,
        target_language: str,
    ) -> list[SubtitleSegment]:
        segments: list[SubtitleSegment] = []
        previous_end = 0.0
        for result in results:
            alternative = result.alternatives[0] if result.alternatives else None
            if not alternative or not alternative.transcript.strip():
                continue
            end_seconds = _duration_to_seconds(result.result_end_offset)
            start_seconds = previous_end
            if alternative.words:
                start_seconds = _duration_to_seconds(alternative.words[0].start_offset)
                end_seconds = _duration_to_seconds(alternative.words[-1].end_offset)
            text = alternative.transcript.strip()
            source_language = normalize_translate_language(result.language_code)
            translation = self._translator.translate(
                text,
                target_language=target_language,
                source_language=source_language,
            )
            segments.append(
                SubtitleSegment(
                    start_seconds=start_seconds,
                    end_seconds=end_seconds,
                    text=text,
                    translation=translation,
                    source_language=result.language_code,
                )
            )
            previous_end = end_seconds
        return segments

    @staticmethod
    def _bucket_location_for_speech(speech_location: str) -> str:
        mapping = {
            "global": "US",
            "us": "US",
            "eu": "EU",
            "asia-northeast1": "ASIA-NORTHEAST1",
        }
        return mapping.get(speech_location, "US")


def save_upload_copy(file_path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    copy_path = destination_dir / file_path.name
    shutil.copy2(file_path, copy_path)
    return copy_path


def _duration_to_seconds(duration) -> float:
    if duration is None:
        return 0.0
    if hasattr(duration, "total_seconds"):
        return float(duration.total_seconds())
    seconds = getattr(duration, "seconds", 0)
    nanos = getattr(duration, "nanos", 0)
    microseconds = getattr(duration, "microseconds", 0)
    return float(seconds) + (float(nanos) / 1_000_000_000) + (float(microseconds) / 1_000_000)
