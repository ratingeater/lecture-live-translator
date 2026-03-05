from app.services.subtitles import SubtitleSegment, build_srt


def test_build_srt_bilingual() -> None:
    content = build_srt(
        [
            SubtitleSegment(
                start_seconds=0.2,
                end_seconds=3.4,
                text="Hello world.",
                translation="你好，世界。",
            )
        ]
    )
    assert "00:00:00,200 --> 00:00:03,400" in content
    assert "Hello world." in content
    assert "你好，世界。" in content
