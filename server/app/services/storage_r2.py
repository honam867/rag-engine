"""Cloudflare R2 storage wrapper (S3-compatible).

Phase 1: only upload_file is expected to be used.
Updated to run blocking I/O in threadpool for FastAPI async compatibility.
"""

import boto3
from functools import lru_cache
from starlette.concurrency import run_in_threadpool

from server.app.core.config import get_settings


@lru_cache(maxsize=1)
def _get_client_and_bucket():
    settings = get_settings()
    if not settings.r2.endpoint or not settings.r2.access_key_id or not settings.r2.secret_access_key:
        return None, None
    client = boto3.client(
        "s3",
        endpoint_url=settings.r2.endpoint,
        aws_access_key_id=settings.r2.access_key_id,
        aws_secret_access_key=settings.r2.secret_access_key,
    )
    return client, settings.r2.bucket


def _upload_file_sync(file_bytes: bytes, key: str, content_type: str | None = None) -> None:
    """Synchronous upload function to be run in a thread."""
    client, bucket = _get_client_and_bucket()
    if client is None or bucket is None:
        raise RuntimeError("Cloudflare R2 configuration missing. Cannot upload file.")
    
    extra_args = {"ContentType": content_type} if content_type else None
    client.put_object(Bucket=bucket, Key=key, Body=file_bytes, **(extra_args or {}))


async def upload_file(file_bytes: bytes, key: str, content_type: str | None = None) -> None:
    """Async wrapper for uploading file to R2 (runs in threadpool)."""
    await run_in_threadpool(_upload_file_sync, file_bytes, key, content_type)


def check_r2_config_ready() -> bool:
    """Return True if R2 settings are present; log warning once if missing."""
    client, bucket = _get_client_and_bucket()
    if client is None or bucket is None:
        import logging
        logging.getLogger(__name__).warning("Cloudflare R2 configuration missing; uploads will fail.")
        return False
    return True


def download_file(key: str) -> bytes:
    # Phase 2
    raise NotImplementedError


def upload_json(obj: dict, key: str) -> None:
    # Phase 2
    raise NotImplementedError


def download_json(key: str) -> dict:
    # Phase 2
    raise NotImplementedError