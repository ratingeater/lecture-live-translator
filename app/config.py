from __future__ import annotations

import shutil

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Lecture Live Translator"
    app_host: str = "127.0.0.1"
    app_port: int = 8765
    google_cloud_project: str | None = None
    speech_location: str = "global"
    translation_location: str = "global"
    recognizer_id: str = "_"
    default_target_language: str = "zh-CN"
    default_source_language: str = "en-US"
    auto_detect_languages: list[str] = Field(
        default_factory=lambda: ["ru-RU", "en-US", "ja-JP"]
    )
    manual_stream_model: str = "chirp_3"
    auto_stream_model: str = "long"
    batch_model: str = "chirp_3"
    audio_sample_rate_hz: int = 16000
    audio_channel_count: int = 1
    upload_bucket: str | None = None
    temp_dir: Path = Path(".runtime")
    ffmpeg_binary: str = Field(default_factory=lambda: _detect_binary("ffmpeg"))
    translate_interim_results: bool = True
    interim_translation_min_chars: int = 12
    interim_translation_min_interval_ms: int = 1200
    streaming_restart_ms: int = 240000


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.temp_dir.mkdir(parents=True, exist_ok=True)
    return settings


def _detect_binary(binary_name: str) -> str:
    detected = shutil.which(binary_name)
    if detected:
        return detected

    if binary_name == "ffmpeg":
        candidates = [
            Path(
                r"C:\Users\admin\AppData\Local\Microsoft\WinGet\Packages"
                r"\Gyan.FFmpeg.Essentials_Microsoft.Winget.Source_8wekyb3d8bbwe"
                r"\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"
            ),
        ]
        for candidate in candidates:
            if candidate.exists():
                return str(candidate)
    return binary_name
