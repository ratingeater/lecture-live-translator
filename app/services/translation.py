from __future__ import annotations

import threading

from google.cloud import translate_v3


class TranslationService:
    def __init__(self, project_id: str, location: str = "global") -> None:
        self._project_id = project_id
        self._location = location
        self._parent = f"projects/{project_id}/locations/{location}"
        self._client = translate_v3.TranslationServiceClient()
        self._cache: dict[tuple[str, str, str | None], str] = {}
        self._lock = threading.Lock()

    def translate(
        self,
        text: str,
        *,
        target_language: str,
        source_language: str | None = None,
    ) -> str:
        text = text.strip()
        if not text:
            return ""

        key = (text, target_language, source_language)
        with self._lock:
            cached = self._cache.get(key)
        if cached is not None:
            return cached

        request = {
            "parent": self._parent,
            "contents": [text],
            "mime_type": "text/plain",
            "target_language_code": target_language,
        }
        if source_language:
            request["source_language_code"] = source_language
        response = self._client.translate_text(request=request)
        translated = response.translations[0].translated_text if response.translations else ""

        with self._lock:
            if len(self._cache) > 1024:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = translated
        return translated
