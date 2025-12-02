"""Cloudflare R2 storage wrapper (S3-compatible).

Phase 1: only upload_file is expected to be used.
Updated to run blocking I/O in threadpool for FastAPI async compatibility.
"""

import json
from functools import lru_cache
from typing import Any, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from starlette.concurrency import run_in_threadpool

from server.app.core.config import get_settings


@lru_cache(maxsize=1)
def _get_client_and_bucket() -> Tuple[Any | None, str | None]:
    settings = get_settings()
    if not settings.r2.endpoint or not settings.r2.access_key_id or not settings.r2.secret_access_key:
        return None, None
    config = Config(
        max_pool_connections=20,
        retries={"max_attempts": 3, "mode": "standard"},
        tcp_keepalive=True,
    )
    client = boto3.client(
        "s3",
        endpoint_url=settings.r2.endpoint,
        aws_access_key_id=settings.r2.access_key_id,
        aws_secret_access_key=settings.r2.secret_access_key,
        config=config,
    )
    return client, settings.r2.bucket


def _upload_file_sync(file_bytes: bytes, key: str, content_type: str | None = None) -> None:
    """Synchronous upload function to be run in a thread."""
    client, bucket = _get_client_and_bucket()
    if client is None or bucket is None:
        raise RuntimeError("Cloudflare R2 configuration missing. Cannot upload file.")

    extra_args = {"ContentType": content_type} if content_type else {}
    try:
        client.put_object(Bucket=bucket, Key=key, Body=file_bytes, **extra_args)
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - thin wrapper
        raise RuntimeError(f"Failed to upload file to R2: {exc}") from exc


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


def _download_file_sync(key: str) -> bytes:
    """Synchronous download helper to be run in a thread."""
    client, bucket = _get_client_and_bucket()
    if client is None or bucket is None:
        raise RuntimeError("Cloudflare R2 configuration missing. Cannot download file.")

    try:
        obj = client.get_object(Bucket=bucket, Key=key)
        body = obj["Body"].read()
        return body
    except (BotoCoreError, ClientError) as exc:  # pragma: no cover - thin wrapper
        raise RuntimeError(f"Failed to download file from R2: {exc}") from exc


async def download_file(key: str) -> bytes:
    """Async wrapper for downloading file bytes from R2."""
    return await run_in_threadpool(_download_file_sync, key)


def _upload_json_sync(obj: dict, key: str) -> None:
    """Synchronous JSON upload helper."""
    data = json.dumps(obj).encode("utf-8")
    _upload_file_sync(data, key, content_type="application/json")


async def upload_json(obj: dict, key: str) -> None:
    """Async wrapper for uploading JSON object to R2."""
    await run_in_threadpool(_upload_json_sync, obj, key)


def _download_json_sync(key: str) -> dict:
    """Synchronous JSON download helper."""
    raw = _download_file_sync(key)
    try:
        return json.loads(raw.decode("utf-8"))
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise RuntimeError(f"Failed to decode JSON from R2 object {key}: {exc}") from exc


async def download_json(key: str) -> dict:
    """Async wrapper for downloading and parsing JSON from R2."""
    return await run_in_threadpool(_download_json_sync, key)
