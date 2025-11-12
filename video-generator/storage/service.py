# video-generator/storage/service.py
"""
Video Storage Service - High-level API for saving karaoke videos.
"""
import os
import uuid
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .s3client import S3Client
from .repository import KaraokeRepository
from .models import KaraokeEntity, FileMeta, Ids, State

logger = logging.getLogger(__name__)


class VideoStorageService:
    """
    Service for storing completed karaoke videos.
    Handles both S3/MinIO upload and MongoDB metadata.
    """
    
    def __init__(
        self,
        s3_client: S3Client,
        repository: KaraokeRepository
    ):
        """
        Initialize video storage service.
        
        Args:
            s3_client: S3-compatible storage client
            repository: MongoDB repository
        """
        self.s3_client = s3_client
        self.repository = repository
    
    def save_video(
        self,
        job_id: str,
        video_path: str,
        youtube_id: Optional[str] = None,
        cleanup_local: bool = True
    ) -> KaraokeEntity:
        """
        Save a completed karaoke video to storage.
        
        Args:
            job_id: Unique job identifier
            video_path: Path to local video file
            youtube_id: Optional YouTube video ID
            cleanup_local: Whether to delete local file after upload
            
        Returns:
            KaraokeEntity with saved data
            
        Raises:
            FileNotFoundError: If video file doesn't exist
            Exception: If upload or save fails
        """
        try:
            logger.info(f"💾 Saving karaoke video: {job_id}")
            
            if not os.path.exists(video_path):
                raise FileNotFoundError(f"Video file not found: {video_path}")
            
            # Generate UUIDs
            file_uuid = str(uuid.uuid4())
            filename = Path(video_path).name
            
            # Upload to S3/MinIO
            logger.info(f"  📤 Uploading to {self.s3_client.bucket_name}...")
            object_name, file_size = self.s3_client.upload_file(
                file_path=video_path,
                object_name=f"{file_uuid}_{filename}",
                content_type='video/mp4',
                metadata={
                    'job_id': job_id,
                    'youtube_id': youtube_id or ''
                }
            )
            
            # Create entity
            now = datetime.now()
            entity = KaraokeEntity(
                job_id=job_id,
                state=State.FINISHED,
                ids=Ids(youtube=youtube_id),
                file_meta=FileMeta(
                    file_uuid=file_uuid,
                    bucket=self.s3_client.bucket_name,
                    object_name=object_name,
                    file_name=filename,
                    file_size=file_size,
                    mime_type='video/mp4'
                ),
                created_at=now,
                updated_at=now
            )
            
            # Save to MongoDB
            logger.info(f"  💾 Saving metadata to MongoDB...")
            inserted_id = self.repository.insert(entity)
            entity._id = inserted_id
            
            logger.info(
                f"✅ Video saved: job_id={job_id}, "
                f"object={object_name}, size={file_size} bytes"
            )
            
            # Clean up local file
            if cleanup_local:
                try:
                    os.remove(video_path)
                    logger.info(f"  🗑️  Removed local file: {video_path}")
                except Exception as e:
                    logger.warning(f"Could not remove local file: {e}")
            
            return entity
            
        except Exception as e:
            logger.error(f"❌ Failed to save video: {e}", exc_info=True)
            raise
    
    def get_video(self, job_id: str) -> Optional[KaraokeEntity]:
        """
        Retrieve video metadata by job_id.
        
        Args:
            job_id: Job identifier
            
        Returns:
            KaraokeEntity or None if not found
        """
        return self.repository.find_by_job_id(job_id)
    
    def get_video_url(self, job_id: str, expires_hours: int = 24) -> Optional[str]:
        """
        Get a presigned URL for video download.
        
        Args:
            job_id: Job identifier
            expires_hours: URL expiration time
            
        Returns:
            Presigned URL or None if video not found
        """
        entity = self.get_video(job_id)
        if not entity:
            return None
        
        return self.s3_client.get_presigned_url(
            entity.file_meta.object_name,
            expires_hours=expires_hours
        )
    
    def list_finished_videos(self, limit: int = 100) -> list[KaraokeEntity]:
        """
        List all finished karaoke videos.
        
        Args:
            limit: Maximum number of results
            
        Returns:
            List of KaraokeEntity
        """
        return self.repository.find_by_state(State.FINISHED, limit=limit)
    
    def delete_video(self, job_id: str) -> bool:
        """
        Delete a video from both S3 and MongoDB.
        
        Args:
            job_id: Job identifier
            
        Returns:
            True if deleted successfully
        """
        try:
            entity = self.get_video(job_id)
            if not entity:
                logger.warning(f"Video not found: {job_id}")
                return False
            
            # Delete from S3
            self.s3_client.delete_file(entity.file_meta.object_name)
            
            # Delete from MongoDB
            self.repository.delete(entity._id)
            
            logger.info(f"Deleted video: {job_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to delete video: {e}")
            return False
