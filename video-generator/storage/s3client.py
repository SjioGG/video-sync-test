# shared/s3client/client.py
"""
Base S3-compatible storage client.
Works with MinIO, AWS S3, GCS (S3-compatible), and other S3-compatible services.
"""
import os
import uuid
import logging
from typing import Optional
from pathlib import Path
from minio import Minio
from minio.error import S3Error

logger = logging.getLogger(__name__)


class S3Client:
    """
    Base S3-compatible storage client.
    
    Supports:
    - MinIO
    - AWS S3
    - Google Cloud Storage (S3-compatible API)
    - Any S3-compatible storage
    """
    
    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        bucket_name: str,
        secure: bool = False,
        region: Optional[str] = None
    ):
        """
        Initialize S3-compatible client.
        
        Args:
            endpoint: Storage endpoint
                - MinIO: 'localhost:9000'
                - AWS S3: 's3.amazonaws.com'
                - GCS: 'storage.googleapis.com'
            access_key: Access key / Access Key ID
            secret_key: Secret key / Secret Access Key
            bucket_name: Bucket name
            secure: Use HTTPS (True for production, False for local MinIO)
            region: Region (optional, e.g., 'us-east-1', 'europe-west1')
        """
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
            region=region
        )
        self.bucket_name = bucket_name
        self.endpoint = endpoint
        self._ensure_bucket()
    
    def _ensure_bucket(self):
        """Create bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                logger.info(f"Created bucket: {self.bucket_name}")
            else:
                logger.debug(f"Bucket exists: {self.bucket_name}")
        except S3Error as e:
            logger.error(f"Bucket error: {e}")
            raise
    
    def upload_file(
        self,
        file_path: str,
        object_name: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None
    ) -> tuple[str, int]:
        """
        Upload a file to storage.
        
        Args:
            file_path: Path to local file
            object_name: Object name in bucket (auto-generated if None)
            content_type: MIME type (auto-detected if None)
            metadata: Optional metadata dict
            
        Returns:
            Tuple of (object_name, file_size)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        file_size = os.path.getsize(file_path)
        
        if object_name is None:
            filename = Path(file_path).name
            object_name = f"{uuid.uuid4()}_{filename}"
        
        if content_type is None:
            content_type = self._detect_content_type(file_path)
        
        try:
            self.client.fput_object(
                self.bucket_name,
                object_name,
                file_path,
                content_type=content_type,
                metadata=metadata
            )
            logger.info(f"Uploaded: {object_name} ({file_size} bytes) to {self.bucket_name}")
            return object_name, file_size
        except S3Error as e:
            logger.error(f"Upload failed: {e}")
            raise
    
    def download_file(self, object_name: str, file_path: str) -> str:
        """Download a file from storage"""
        try:
            self.client.fget_object(self.bucket_name, object_name, file_path)
            logger.info(f"Downloaded: {object_name} -> {file_path}")
            return file_path
        except S3Error as e:
            logger.error(f"Download failed: {e}")
            raise
    
    def delete_file(self, object_name: str) -> bool:
        """Delete a file from storage"""
        try:
            self.client.remove_object(self.bucket_name, object_name)
            logger.info(f"Deleted: {object_name}")
            return True
        except S3Error as e:
            logger.error(f"Delete failed: {e}")
            raise
    
    def file_exists(self, object_name: str) -> bool:
        """Check if a file exists"""
        try:
            self.client.stat_object(self.bucket_name, object_name)
            return True
        except S3Error:
            return False
    
    def get_presigned_url(self, object_name: str, expires_hours: int = 24) -> str:
        """Get a presigned URL for file access"""
        try:
            from datetime import timedelta
            url = self.client.presigned_get_object(
                self.bucket_name,
                object_name,
                expires=timedelta(hours=expires_hours)
            )
            return url
        except S3Error as e:
            logger.error(f"URL generation failed: {e}")
            raise
    
    def list_files(self, prefix: Optional[str] = None) -> list[str]:
        """List files in bucket with optional prefix filter"""
        try:
            objects = self.client.list_objects(
                self.bucket_name,
                prefix=prefix,
                recursive=True
            )
            return [obj.object_name for obj in objects]
        except S3Error as e:
            logger.error(f"List failed: {e}")
            raise
    
    def _detect_content_type(self, file_path: str) -> str:
        """Auto-detect content type based on file extension"""
        ext = Path(file_path).suffix.lower()
        content_type_map = {
            '.mp4': 'video/mp4',
            '.mp3': 'audio/mpeg',
            '.wav': 'audio/wav',
            '.lrc': 'text/plain',
            '.json': 'application/json',
            '.txt': 'text/plain',
            '.png': 'image/png',
            '.jpg': 'image/jpeg',
            '.jpeg': 'image/jpeg'
        }
        return content_type_map.get(ext, 'application/octet-stream')
