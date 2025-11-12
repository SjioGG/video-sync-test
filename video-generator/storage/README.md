# Video Generator Storage Package

Service-specific storage for completed karaoke videos.

## Purpose

This package is **specific to video-generator service**. It handles:
- Uploading completed videos to S3/MinIO/GCS
- Saving video metadata to MongoDB
- Managing karaoke video lifecycle

Other services (song-downloader, lyrics-fetcher) will have their own storage packages with different data models.

## Architecture

```
video-generator/storage/
├── __init__.py           # Package exports
├── s3client.py           # Base S3 client (copied from shared/s3client)
├── models.py             # KaraokeEntity, FileMeta, State
├── repository.py         # MongoDB operations
└── service.py            # VideoStorageService (high-level API)
```

## Data Model

### KaraokeEntity (Video-Specific)

```python
{
  "_id": ObjectId("..."),
  "job_id": "unique-job-123",    # Primary identifier
  "state": "finished",           # none | processing | finished
  "ids": {
    "youtube": "video_id"        # YouTube ID
  },
  "file_meta": {                 # Embedded file metadata
    "file_uuid": "uuid",
    "bucket": "karaoke-videos",
    "object_name": "uuid_file.mp4",
    "file_name": "video.mp4",
    "file_size": 12345678,
    "mime_type": "video/mp4"
  },
  "created_at": ISODate("..."),
  "updated_at": ISODate("...")
}
```

## Usage

### Initialize Storage

```python
from storage import S3Client, KaraokeRepository, VideoStorageService
from pymongo import MongoClient

# S3 Client (MinIO, AWS S3, or GCS)
s3_client = S3Client(
    endpoint='minio:9000',           # or 's3.amazonaws.com' or 'storage.googleapis.com'
    access_key='minioadmin',
    secret_key='minioadmin',
    bucket_name='karaoke-videos',
    secure=False                      # True for production
)

# MongoDB Repository
mongo_client = MongoClient('mongodb://admin:password@mongodb:27017/')
repository = KaraokeRepository(mongo_client['karaoke']['karaoke_entities'])

# High-level Storage Service
video_storage = VideoStorageService(s3_client, repository)
```

### Save Completed Video

```python
# After generating video with moviepy
entity = video_storage.save_video(
    job_id='unique-job-123',
    video_path='/app/shared/videos/job-123.mp4',
    youtube_id='abc123',
    cleanup_local=True  # Delete local file after upload
)

print(f"Saved: {entity.job_id}")
print(f"Object: {entity.file_meta.object_name}")
print(f"Size: {entity.file_meta.file_size} bytes")
```

### Query Videos

```python
# Get specific video
video = video_storage.get_video('unique-job-123')

# Get presigned download URL
url = video_storage.get_video_url('unique-job-123', expires_hours=24)

# List finished videos
videos = video_storage.list_finished_videos(limit=10)

# Delete video
video_storage.delete_video('unique-job-123')
```

## Environment Variables

```bash
# S3/MinIO/GCS Configuration
S3_ENDPOINT=minio:9000              # or s3.amazonaws.com, storage.googleapis.com
S3_ACCESS_KEY=minioadmin
S3_SECRET_KEY=minioadmin
S3_BUCKET=karaoke-videos
S3_SECURE=false                     # true for production

# MongoDB Configuration
MONGODB_URI=mongodb://admin:password@mongodb:27017/
```

## S3-Compatible Storage Support

### MinIO (Local Development)
```python
S3Client(
    endpoint='minio:9000',
    access_key='minioadmin',
    secret_key='minioadmin',
    bucket_name='karaoke-videos',
    secure=False
)
```

### AWS S3 (Production)
```python
S3Client(
    endpoint='s3.amazonaws.com',
    access_key='AKIAIOSFODNN7EXAMPLE',
    secret_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
    bucket_name='my-production-bucket',
    secure=True,
    region='us-east-1'
)
```

### Google Cloud Storage (S3-compatible API)
```python
S3Client(
    endpoint='storage.googleapis.com',
    access_key='YOUR_GCS_ACCESS_KEY',
    secret_key='YOUR_GCS_SECRET_KEY',
    bucket_name='my-gcs-bucket',
    secure=True,
    region='us-central1'
)
```

## Integration with main.py

```python
# video-generator/main.py
from storage import S3Client, KaraokeRepository, VideoStorageService
from pymongo import MongoClient

# Initialize on startup
video_storage = None

def init_storage():
    global video_storage
    s3_client = S3Client(...)
    repository = KaraokeRepository(...)
    video_storage = VideoStorageService(s3_client, repository)

# Use in video processing
def process_video_request(message):
    # ... generate video ...
    
    video_storage.save_video(
        job_id=message['job_id'],
        video_path=output_path,
        youtube_id=message.get('youtube_id')
    )
```

## Why Service-Specific?

Each service stores **different data**:

- **video-generator/storage/** - KaraokeEntity (finished videos)
- **song-downloader/storage/** - DownloadMetadata (YouTube downloads)
- **lyrics-fetcher/storage/** - LyricsCache (cached lyrics)

By having separate storage packages, each service:
- ✅ Defines its own data models
- ✅ Has its own MongoDB collections
- ✅ Remains independent
- ✅ Can be extracted to its own repository later

## Reusability

The **S3Client** (s3client.py) is copied from `shared/s3client/`. This base client is reusable across all services, but each service has its own copy to remain independent.

When splitting into multiple repos, each service brings its storage package with it.
