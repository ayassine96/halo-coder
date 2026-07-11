#!/usr/bin/env python3
"""S3-compatible MinIO client for HALO artifact storage."""

import io
import os


class MinioClient:
    """Thin wrapper over minio-py for artifact upload/download."""

    def __init__(self, endpoint="localhost:9000", access_key=None, secret_key=None, secure=False, bucket="halo-artifacts"):
        from minio import Minio
        self._client = Minio(
            endpoint,
            access_key=access_key or "",
            secret_key=secret_key or "",
            secure=secure,
        )
        self._bucket = bucket
        self._ensure_bucket()

    def _ensure_bucket(self):
        try:
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
        except Exception:
            pass

    def upload(self, object_name, data, content_type="application/octet-stream", metadata=None):
        """Upload artifact to bucket.

        Args:
            object_name: Path within bucket (e.g. artifacts/demo/SPEC-001/junit.xml).
            data: bytes or file-like object.
            content_type: MIME type.
            metadata: Optional dict of metadata.
        """
        if isinstance(data, bytes):
            stream = io.BytesIO(data)
            length = len(data)
        elif isinstance(data, str):
            raw = data.encode("utf-8")
            stream = io.BytesIO(raw)
            length = len(raw)
        else:
            stream = data
            length = os.stat(stream.name).st_size if hasattr(stream, "name") else -1
        return self._client.put_object(
            self._bucket, object_name, stream, length, content_type=content_type, metadata=metadata
        )

    def download(self, object_name):
        """Download artifact from bucket. Returns bytes."""
        response = self._client.get_object(self._bucket, object_name)
        return response.read()

    def list_objects(self, prefix=""):
        """List objects in bucket with optional prefix."""
        return list(self._client.list_objects(self._bucket, prefix=prefix))

    def upload_file(self, file_path, object_name=None):
        """Upload a file from the filesystem."""
        object_name = object_name or os.path.basename(file_path)
        size = os.stat(file_path).st_size
        with open(file_path, "rb") as f:
            return self.upsert_upload(object_name, f, length=size)

    def upsert_upload(self, object_name, stream, length):
        """Internal: upload from stream with known length."""
        return self._client.put_object(self._bucket, object_name, stream, length)

    def delete(self, object_name):
        return self._client.remove_object(self._bucket, object_name)