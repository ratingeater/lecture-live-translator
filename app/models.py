from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, field_validator


class StreamStartPayload(BaseModel):
    project_id: str | None = None
    speech_location: str | None = None
    recognizer_id: str | None = None
    source_mode: Literal["manual", "auto"] = "manual"
    source_language: str | None = "en-US"
    auto_languages: list[str] | None = None
    target_language: str = "zh-CN"
    sample_rate_hz: int = 16000
    channel_count: int = 1
    translate_interim: bool = True

    @field_validator("auto_languages")
    @classmethod
    def limit_auto_languages(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        unique = list(dict.fromkeys(value))
        if len(unique) > 3:
            raise ValueError("auto_languages can contain at most 3 language codes.")
        return unique

    @property
    def source_language_codes(self) -> list[str]:
        if self.source_mode == "auto":
            return self.auto_languages or []
        return [self.source_language] if self.source_language else []


class StreamEvent(BaseModel):
    type: Literal["status", "transcript", "error"]
    message: str | None = None
    transcript: str | None = None
    translation: str | None = None
    is_final: bool | None = None
    language_code: str | None = None
    start_offset: float | None = None
    end_offset: float | None = None


class BatchTranscribeResponse(BaseModel):
    source_language: str | None
    target_language: str
    transcript_text: str
    translation_text: str
    srt_content: str
    srt_path: str
    transcript_path: str
