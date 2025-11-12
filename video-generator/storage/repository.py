# shared/storage/repository.py
"""MongoDB repository for karaoke entities"""
import logging
from typing import Optional, List
from datetime import datetime
from bson import ObjectId
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.errors import PyMongoError

from .models import KaraokeEntity, State

logger = logging.getLogger(__name__)


class KaraokeRepository:
    """Repository for karaoke entity CRUD operations"""
    
    def __init__(self, collection: Collection):
        """
        Initialize repository with MongoDB collection.
        
        Args:
            collection: MongoDB collection instance
        """
        self.collection = collection
        self._create_indexes()
    
    def _create_indexes(self):
        """Create indexes for efficient querying"""
        try:
            # job_id is unique identifier
            self.collection.create_index('job_id', unique=True)
            self.collection.create_index('state')
            self.collection.create_index('created_at')
            logger.info("Created indexes on karaoke_entities collection")
        except PyMongoError as e:
            logger.error(f"Failed to create indexes: {e}")
    
    def insert(self, entity: KaraokeEntity) -> ObjectId:
        """Insert a new karaoke entity"""
        try:
            result = self.collection.insert_one(entity.to_dict())
            logger.info(f"Inserted entity: job_id={entity.job_id}, _id={result.inserted_id}")
            return result.inserted_id
        except PyMongoError as e:
            logger.error(f"Failed to insert entity: {e}")
            raise
    
    def find_by_id(self, entity_id: ObjectId) -> Optional[KaraokeEntity]:
        """Find entity by MongoDB _id"""
        try:
            doc = self.collection.find_one({'_id': entity_id})
            return KaraokeEntity.from_dict(doc) if doc else None
        except PyMongoError as e:
            logger.error(f"Failed to find entity by _id: {e}")
            raise
    
    def find_by_job_id(self, job_id: str) -> Optional[KaraokeEntity]:
        """Find entity by job_id"""
        try:
            doc = self.collection.find_one({'job_id': job_id})
            return KaraokeEntity.from_dict(doc) if doc else None
        except PyMongoError as e:
            logger.error(f"Failed to find entity by job_id: {e}")
            raise
    
    def find_all(self, limit: int = 100, skip: int = 0) -> List[KaraokeEntity]:
        """Find all entities with pagination"""
        try:
            cursor = self.collection.find({}).sort('created_at', -1).skip(skip).limit(limit)
            return [KaraokeEntity.from_dict(doc) for doc in cursor]
        except PyMongoError as e:
            logger.error(f"Failed to find all entities: {e}")
            raise
    
    def find_by_state(self, state: State, limit: int = 100) -> List[KaraokeEntity]:
        """Find entities by state"""
        try:
            cursor = self.collection.find({'state': state.value}).sort('created_at', -1).limit(limit)
            return [KaraokeEntity.from_dict(doc) for doc in cursor]
        except PyMongoError as e:
            logger.error(f"Failed to find entities by state: {e}")
            raise
    
    def update(self, entity: KaraokeEntity) -> bool:
        """Update an existing entity"""
        if entity._id is None:
            raise ValueError("Cannot update entity without _id")
        
        try:
            # Always update the updated_at timestamp
            entity.updated_at = datetime.now()
            
            result = self.collection.update_one(
                {'_id': entity._id},
                {'$set': entity.to_dict()}
            )
            
            if result.modified_count > 0:
                logger.info(f"Updated entity: job_id={entity.job_id}")
                return True
            return False
        except PyMongoError as e:
            logger.error(f"Failed to update entity: {e}")
            raise
    
    def delete(self, entity_id: ObjectId) -> bool:
        """Delete an entity by _id"""
        try:
            result = self.collection.delete_one({'_id': entity_id})
            if result.deleted_count > 0:
                logger.info(f"Deleted entity: _id={entity_id}")
                return True
            return False
        except PyMongoError as e:
            logger.error(f"Failed to delete entity: {e}")
            raise
    
    def count(self) -> int:
        """Count total entities"""
        try:
            return self.collection.count_documents({})
        except PyMongoError as e:
            logger.error(f"Failed to count entities: {e}")
            raise
