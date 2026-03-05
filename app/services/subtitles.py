from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SubtitleSegment:
    start_seconds: float
    end_seconds: float
    text: str
    translation: str = ""
    source_language: str | None = None


def _format_srt_timestamp(total_seconds: float) -> str:
    if total_seconds < 0:
        total_seconds = 0
    total_ms = int(round(total_seconds * 1000))
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{milliseconds:03}"


def build_srt(segments: list[SubtitleSegment]) -> str:
    lines: list[str] = []
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(
            f"{_format_srt_timestamp(segment.start_seconds)} --> "
            f"{_format_srt_timestamp(segment.end_seconds)}"
        )
        lines.append(segment.text.strip())
        if segment.translation.strip():
            lines.append(segment.translation.strip())
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_plain_text(segments: list[SubtitleSegment], translated: bool = False) -> str:
    chunks = [segment.translation if translated else segment.text for segment in segments]
    return "\n".join(chunk.strip() for chunk in chunks if chunk.strip()) + "\n"


def save_outputs(output_dir: Path, stem: str, segments: list[SubtitleSegment]) -> tuple[Path, Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    srt_path = output_dir / f"{stem}.srt"
    transcript_path = output_dir / f"{stem}.txt"
    translation_path = output_dir / f"{stem}.translated.txt"
    srt_path.write_text(build_srt(segments), encoding="utf-8")
    transcript_path.write_text(build_plain_text(segments), encoding="utf-8")
    translation_path.write_text(build_plain_text(segments, translated=True), encoding="utf-8")
    return srt_path, transcript_path, translation_path
