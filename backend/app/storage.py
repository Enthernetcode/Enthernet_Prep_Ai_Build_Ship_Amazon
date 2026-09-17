from __future__ import annotations

import asyncio
from functools import lru_cache

import boto3
from botocore.client import BaseClient
from botocore.config import Config
from botocore.exceptions import ClientError

from app.config import settings


def _make_client(endpoint: str) -> BaseClient:
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
        config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
    )


@lru_cache
def _client() -> BaseClient:
    return _make_client(settings.s3_endpoint_url)


@lru_cache
def _public_client() -> BaseClient:
    public = settings.s3_public_endpoint_url or settings.s3_endpoint_url
    return _make_client(public)


async def ensure_bucket() -> None:
    def _sync() -> None:
        client = _client()
        try:
            client.head_bucket(Bucket=settings.s3_bucket)
        except ClientError as exc:
            code = exc.response.get("Error", {}).get("Code", "")
            if code not in {"404", "NoSuchBucket", "NoSuchKey"}:
                if code != "":
                    raise
            client.create_bucket(Bucket=settings.s3_bucket)

    await asyncio.to_thread(_sync)


async def put_object(key: str, body: bytes, content_type: str) -> None:
    def _sync() -> None:
        _client().put_object(
            Bucket=settings.s3_bucket, Key=key, Body=body, ContentType=content_type
        )

    await asyncio.to_thread(_sync)


async def delete_object(key: str) -> None:
    def _sync() -> None:
        _client().delete_object(Bucket=settings.s3_bucket, Key=key)

    await asyncio.to_thread(_sync)


async def presigned_get_url(key: str, expires_in: int | None = None) -> str:
    ttl = expires_in or settings.document_presign_ttl_seconds

    def _sync() -> str:
        return _public_client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.s3_bucket, "Key": key},
            ExpiresIn=ttl,
        )

    return await asyncio.to_thread(_sync)
