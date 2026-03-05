from __future__ import annotations

from pathlib import Path

from google.cloud import storage


class StorageService:
    def __init__(self, project_id: str) -> None:
        self._project_id = project_id
        self._client = storage.Client(project=project_id)

    def ensure_bucket(self, bucket_name: str, *, location: str) -> storage.Bucket:
        bucket = self._client.bucket(bucket_name)
        if bucket.exists():
            return bucket
        bucket.storage_class = "STANDARD"
        return self._client.create_bucket(bucket, location=location)

    def upload_file(
        self,
        *,
        bucket_name: str,
        local_path: Path,
        blob_name: str,
        content_type: str = "audio/flac",
    ) -> str:
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        blob.upload_from_filename(str(local_path), content_type=content_type)
        return f"gs://{bucket_name}/{blob_name}"

    def delete_blob(self, bucket_name: str, blob_name: str) -> None:
        bucket = self._client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        if blob.exists():
            blob.delete()
