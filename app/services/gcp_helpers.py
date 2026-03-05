from __future__ import annotations

from google.cloud.speech_v2.types import cloud_speech


def build_recognizer_name(project_id: str, location: str, recognizer_id: str) -> str:
    return f"projects/{project_id}/locations/{location}/recognizers/{recognizer_id}"


def choose_speech_model(*, streaming: bool, auto_detect: bool, location: str) -> str:
    if location == "global":
        return "long"
    if auto_detect:
        return "long"
    return "chirp_3" if streaming else "chirp_3"


def normalize_translate_language(code: str | None) -> str | None:
    if not code:
        return None
    if code.lower() == "zh-cn":
        return "zh-CN"
    if "-" in code:
        return code.split("-", 1)[0]
    return code


def build_streaming_recognition_config(
    *,
    language_codes: list[str],
    model: str,
    sample_rate_hz: int,
    channel_count: int,
    interim_results: bool,
) -> cloud_speech.StreamingRecognitionConfig:
    config = cloud_speech.RecognitionConfig(
        explicit_decoding_config=cloud_speech.ExplicitDecodingConfig(
            encoding=cloud_speech.ExplicitDecodingConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=sample_rate_hz,
            audio_channel_count=channel_count,
        ),
        language_codes=language_codes,
        model=model,
        features=cloud_speech.RecognitionFeatures(
            enable_automatic_punctuation=True,
            enable_spoken_punctuation=True,
            enable_word_time_offsets=True,
        ),
    )
    return cloud_speech.StreamingRecognitionConfig(
        config=config,
        streaming_features=cloud_speech.StreamingRecognitionFeatures(
            interim_results=interim_results,
            enable_voice_activity_events=True,
        ),
    )


def build_batch_recognition_config(
    *,
    language_codes: list[str],
    model: str,
    use_header_detection: bool = True,
) -> cloud_speech.RecognitionConfig:
    kwargs: dict[str, object] = {
        "language_codes": language_codes,
        "model": model,
        "features": cloud_speech.RecognitionFeatures(
            enable_automatic_punctuation=True,
            enable_word_time_offsets=True,
        ),
    }
    if use_header_detection:
        kwargs["auto_decoding_config"] = cloud_speech.AutoDetectDecodingConfig()
    return cloud_speech.RecognitionConfig(**kwargs)
