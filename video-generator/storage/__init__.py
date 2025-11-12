"""
Video Generator Storage Package

Service-specific storage for karaoke videos.
Uses base S3Client for object storage and MongoDB for metadata.
"""
from .models import State, Ids, FileMeta, KaraokeEntity
from .repository import KaraokeRepository
from .s3client import S3Client
from .service import VideoStorageService

__all__ = [
    'State',
    'Ids',
    'FileMeta',
    'KaraokeEntity',
    'KaraokeRepository',
    'S3Client',
    'VideoStorageService'
]
