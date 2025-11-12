# shared/storage/models.py
"""
Data models for karaoke storage.
Simplified: Uses job_id as primary identifier (no separate karaoke_id).
"""
from dataclasses import dataclass
from typing import Optional
from datetime import datetime
from enum import Enum
from bson import ObjectId


class State(Enum):
    """Processing state of karaoke entity"""
    NONE = "none"
    PROCESSING = "processing"
    FINISHED = "finished"


@dataclass
class Ids:
    """External identifiers"""
    youtube: Optional[str] = None


@dataclass
class FileMeta:
    """File metadata (embedded in KaraokeEntity)"""
    file_uuid: str
    bucket: str
    object_name: str
    file_name: str
    file_size: int
    mime_type: str


@dataclass
class KaraokeEntity:
    """
    Main karaoke entity with embedded file metadata.
    Simplified: Uses job_id as primary identifier.
    """
    job_id: str  # Primary identifier (unique)
    state: State
    ids: Ids
    file_meta: FileMeta
    created_at: datetime
    updated_at: datetime
    _id: Optional[ObjectId] = None
    
    def to_dict(self) -> dict:
        """Convert to MongoDB document"""
        doc = {
            'job_id': self.job_id,
            'state': self.state.value,
            'ids': {
                'youtube': self.ids.youtube
            },
            'file_meta': {
                'file_uuid': self.file_meta.file_uuid,
                'bucket': self.file_meta.bucket,
                'object_name': self.file_meta.object_name,
                'file_name': self.file_meta.file_name,
                'file_size': self.file_meta.file_size,
                'mime_type': self.file_meta.mime_type
            },
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }
        if self._id is not None:
            doc['_id'] = self._id
        return doc
    
    @staticmethod
    def from_dict(doc: dict) -> 'KaraokeEntity':
        """Create from MongoDB document"""
        return KaraokeEntity(
            _id=doc.get('_id'),
            job_id=doc['job_id'],
            state=State(doc['state']),
            ids=Ids(youtube=doc['ids'].get('youtube')),
            file_meta=FileMeta(
                file_uuid=doc['file_meta']['file_uuid'],
                bucket=doc['file_meta']['bucket'],
                object_name=doc['file_meta']['object_name'],
                file_name=doc['file_meta']['file_name'],
                file_size=doc['file_meta']['file_size'],
                mime_type=doc['file_meta']['mime_type']
            ),
            created_at=doc['created_at'],
            updated_at=doc['updated_at']
        )
