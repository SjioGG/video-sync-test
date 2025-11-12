"""
Reusable S3/MinIO base client.
Works with MinIO, AWS S3, GCS (S3-compatible API), and other S3-compatible storage.

This is a base component that can be used by any service that needs object storage.
Each service creates its own storage package that uses this base client.
"""
from .client import S3Client

__all__ = ['S3Client']
