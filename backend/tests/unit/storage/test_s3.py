"""Unit tests for app/storage/s3.py with aioboto3 mocks."""

from __future__ import annotations

import datetime as _dt
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from botocore.exceptions import ClientError

from app.storage.s3 import S3Storage


class _FakeS3Client:
    def __init__(self):
        self.head_bucket = AsyncMock()
        self.create_bucket = AsyncMock()
        self.upload_fileobj = AsyncMock()
        self.get_object = AsyncMock()
        self.delete_object = AsyncMock()
        self.head_object = AsyncMock()
        self.generate_presigned_url = AsyncMock(return_value="http://minio:9000/b/key")

    def get_paginator(self, _name):
        async def _paginate(**_kw):
            yield {
                "Contents": [
                    {
                        "Key": "a.txt",
                        "Size": 1,
                        "LastModified": _dt.datetime(2026, 1, 1),
                    },
                ]
            }

        m = MagicMock()
        m.paginate = _paginate
        return m


def _patch_get_client(storage: S3Storage, client: _FakeS3Client):
    @asynccontextmanager
    async def _gc():
        yield client

    storage.get_client = _gc  # type: ignore[assignment]


@pytest.fixture
def storage() -> S3Storage:
    return S3Storage()


async def test_ensure_bucket_exists_when_present(storage):
    fake = _FakeS3Client()
    _patch_get_client(storage, fake)
    await storage.ensure_bucket_exists()
    fake.head_bucket.assert_awaited_once()
    fake.create_bucket.assert_not_awaited()


async def test_ensure_bucket_creates_on_404(storage):
    fake = _FakeS3Client()
    fake.head_bucket.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadBucket")
    _patch_get_client(storage, fake)
    await storage.ensure_bucket_exists()
    fake.create_bucket.assert_awaited_once()


async def test_ensure_bucket_reraises_other_errors(storage):
    fake = _FakeS3Client()
    fake.head_bucket.side_effect = ClientError({"Error": {"Code": "403"}}, "HeadBucket")
    _patch_get_client(storage, fake)
    with pytest.raises(ClientError):
        await storage.ensure_bucket_exists()


async def test_upload_bytes_returns_url(storage):
    fake = _FakeS3Client()
    _patch_get_client(storage, fake)
    url = await storage.upload_bytes(b"data", "k", content_type="text/plain")
    assert url.endswith("/k")
    fake.upload_fileobj.assert_awaited_once()


async def test_download_file_reads_body(storage):
    fake = _FakeS3Client()
    body = MagicMock()
    body.read = AsyncMock(return_value=b"hello")
    fake.get_object.return_value = {"Body": body}
    _patch_get_client(storage, fake)
    assert await storage.download_file("k") == b"hello"


async def test_delete_file_true(storage):
    fake = _FakeS3Client()
    _patch_get_client(storage, fake)
    assert await storage.delete_file("k") is True


async def test_delete_file_returns_false_on_clienterror(storage):
    fake = _FakeS3Client()
    fake.delete_object.side_effect = ClientError(
        {"Error": {"Code": "x"}}, "DeleteObject"
    )
    _patch_get_client(storage, fake)
    assert await storage.delete_file("k") is False


async def test_file_exists_true(storage):
    fake = _FakeS3Client()
    _patch_get_client(storage, fake)
    assert await storage.file_exists("k") is True


async def test_file_exists_false_on_404(storage):
    fake = _FakeS3Client()
    fake.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
    _patch_get_client(storage, fake)
    assert await storage.file_exists("k") is False


async def test_file_exists_reraises_other(storage):
    fake = _FakeS3Client()
    fake.head_object.side_effect = ClientError({"Error": {"Code": "500"}}, "HeadObject")
    _patch_get_client(storage, fake)
    with pytest.raises(ClientError):
        await storage.file_exists("k")


async def test_get_file_url_replaces_endpoint(storage):
    fake = _FakeS3Client()
    fake.generate_presigned_url.return_value = "http://minio:9000/b/key?sig=1"
    _patch_get_client(storage, fake)
    storage.endpoint_url = "http://minio:9000"
    storage.public_url = "http://public:9000"
    url = await storage.get_file_url("k")
    assert url.startswith("http://public:9000")


async def test_list_files_paginates(storage):
    fake = _FakeS3Client()
    _patch_get_client(storage, fake)
    files = await storage.list_files()
    assert files and files[0]["key"] == "a.txt"
