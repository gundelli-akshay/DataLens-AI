"""
services/storage.py - Supabase Object Storage service.

Supabase Storage is the exclusive persistent file-storage backend for DataLens AI.
Local storage fallback is disabled across all environments.

Safety rules:
- SUPABASE_URL and SUPABASE_KEY must be configured.
- Files are stored in the designated Supabase Storage bucket.
- A local cache copy is maintained in upload_dir_path for local processing (PyMuPDF, python-docx, pandas).
- If Supabase upload/download/delete fails, StorageError is raised (no silent local fallbacks).
"""

import logging
from pathlib import Path
from typing import Optional
import httpx

from app.core.config import Settings, settings as global_settings

logger = logging.getLogger(__name__)


class StorageError(Exception):
    """Raised when an object storage operation fails."""
    pass


class StorageService:
    def __init__(self, config: Optional[Settings] = None):
        self.settings = config or global_settings

    @property
    def is_cloud(self) -> bool:
        return self.settings.is_supabase_storage_enabled

    def _get_headers(self) -> dict:
        key = self.settings.supabase_key.strip()
        return {
            "Authorization": f"Bearer {key}",
            "apikey": key,
        }

    def _get_object_url(self, filename: str) -> str:
        base = self.settings.supabase_url.strip().rstrip("/")
        bucket = self.settings.supabase_storage_bucket.strip()
        return f"{base}/storage/v1/object/{bucket}/{filename}"

    def _ensure_bucket(self) -> None:
        """
        Check/create bucket if needed on Supabase (best-effort).
        """
        if not self.is_cloud:
            return
        base = self.settings.supabase_url.strip().rstrip("/")
        bucket = self.settings.supabase_storage_bucket.strip()
        url = f"{base}/storage/v1/bucket"
        try:
            with httpx.Client(timeout=10.0) as client:
                res = client.post(
                    url,
                    headers={**self._get_headers(), "Content-Type": "application/json"},
                    json={"id": bucket, "name": bucket, "public": False},
                )
                if res.status_code in (200, 201, 400, 409):
                    return
        except Exception as exc:
            logger.warning("Could not auto-create Supabase storage bucket: %s", exc)

    def save_file(
        self,
        saved_filename: str,
        content: bytes,
        content_type: str = "application/octet-stream",
    ) -> str:
        """
        Save file content to persistent Supabase Object Storage.
        Creates a local cached copy in upload_dir_path for runtime processing.
        Raises StorageError if Supabase is unconfigured or upload fails.
        """
        if not self.is_cloud:
            raise StorageError(
                "Supabase Storage is the exclusive file storage backend. "
                "SUPABASE_URL and SUPABASE_KEY must be configured."
            )

        url = self._get_object_url(saved_filename)
        headers = {
            **self._get_headers(),
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "true",
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.post(url, headers=headers, content=content)
                if res.status_code not in (200, 201):
                    raise StorageError(
                        f"Supabase upload failed with status {res.status_code}: {res.text}"
                    )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"Supabase storage network error during upload: {str(exc)}") from exc

        # Cache locally for fast runtime processing (Pandas, PyMuPDF, python-docx)
        try:
            local_path = self.settings.upload_dir_path / saved_filename
            local_path.write_bytes(content)
        except Exception as e:
            logger.warning("Failed to write local cache copy of uploaded file: %s", e)

        return saved_filename

    def get_file_path(self, saved_filename: str) -> Path:
        """
        Get local file path for downstream document extraction or analysis.
        If file is not yet cached locally, downloads it from Supabase Storage and caches it.
        Raises StorageError if Supabase is unconfigured or download fails.
        """
        local_path = self.settings.upload_dir_path / saved_filename
        if local_path.exists() and local_path.is_file():
            return local_path

        if not self.is_cloud:
            raise StorageError(
                "Supabase Storage is the exclusive file storage backend. "
                "SUPABASE_URL and SUPABASE_KEY must be configured."
            )

        # Download from Supabase Storage
        url = self._get_object_url(saved_filename)
        headers = self._get_headers()
        try:
            with httpx.Client(timeout=30.0) as client:
                res = client.get(url, headers=headers)
                if res.status_code == 404 or (
                    res.status_code == 400 and any(k in res.text for k in ("NoSuchKey", "not_found", "Object not found"))
                ):
                    raise FileNotFoundError(f"File not found in Supabase storage: {saved_filename}")
                if res.status_code not in (200,):
                    raise StorageError(
                        f"Supabase download failed with status {res.status_code}: {res.text}"
                    )
                local_path.write_bytes(res.content)
                return local_path
        except (FileNotFoundError, StorageError):
            raise
        except Exception as exc:
            raise StorageError(f"Supabase storage network error during download: {str(exc)}") from exc

    def get_file_bytes(self, saved_filename: str) -> bytes:
        """Read and return full file content as bytes."""
        path = self.get_file_path(saved_filename)
        return path.read_bytes()

    def delete_file(self, saved_filename: str) -> bool:
        """
        Delete file from persistent Supabase Storage and local cache.
        Raises StorageError if Supabase is unconfigured or delete fails.
        """
        if not self.is_cloud:
            raise StorageError(
                "Supabase Storage is the exclusive file storage backend. "
                "SUPABASE_URL and SUPABASE_KEY must be configured."
            )

        base = self.settings.supabase_url.strip().rstrip("/")
        bucket = self.settings.supabase_storage_bucket.strip()
        url = f"{base}/storage/v1/object/{bucket}"
        headers = {
            **self._get_headers(),
            "Content-Type": "application/json",
        }
        try:
            with httpx.Client(timeout=15.0) as client:
                res = client.request("DELETE", url, headers=headers, json={"prefixes": [saved_filename]})
                if res.status_code in (404, 405):
                    single_url = self._get_object_url(saved_filename)
                    res = client.delete(single_url, headers=self._get_headers())

                if res.status_code not in (200, 204, 404):
                    raise StorageError(
                        f"Supabase delete failed with status {res.status_code}: {res.text}"
                    )
        except StorageError:
            raise
        except Exception as exc:
            raise StorageError(f"Supabase storage network error during delete: {str(exc)}") from exc

        # Delete local cached copy
        local_path = self.settings.upload_dir_path / saved_filename
        if local_path.exists() and local_path.is_file():
            try:
                local_path.unlink()
            except Exception as e:
                logger.warning("Failed to delete local cache copy: %s", e)
        return True

    def file_exists(self, saved_filename: str) -> bool:
        """Check if file exists in local cache or Supabase Storage."""
        local_path = self.settings.upload_dir_path / saved_filename
        if local_path.exists() and local_path.is_file():
            return True

        if not self.is_cloud:
            return False

        try:
            url = self._get_object_url(saved_filename)
            with httpx.Client(timeout=10.0) as client:
                res = client.head(url, headers=self._get_headers())
                return res.status_code == 200
        except Exception:
            return False


storage_service = StorageService()
