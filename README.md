# Video Sync Test

Simplified karaoke video generation pipeline with persistent storage.

## Architecture

7 services orchestrated with Docker Compose and RabbitMQ:

1. **song-downloader** - Downloads YouTube audio with yt-dlp
2. **audio-separation** - Separates vocals/instrumental using MDX-Net with loading bar progress
3. **lyrics-fetcher** - Fetches synced lyrics from online sources
4. **video-generator** - Creates karaoke videos with Python/moviepy (shows next line faded) and saves to MinIO + MongoDB
5. **rabbitmq** - Message broker for inter-service communication
6. **mongodb** - Document database for karaoke metadata
7. **minio** - S3-compatible object storage for video files

### Shared Storage Library

The `shared/storage/` directory contains a reusable Python library for MinIO and MongoDB operations:
- **models.py** - Data models (KaraokeEntity with embedded FileMeta)
- **repository.py** - MongoDB CRUD operations
- **storage.py** - MinIO file operations

This library can be imported by any service that needs storage capabilities.

## Quick Start

```bash
# Start all services (including MongoDB and MinIO)
docker-compose up -d

# Submit a video request
cd song-downloader
uv run producer.py

# Check progress
docker-compose logs -f song-downloader
docker-compose logs -f audio-separation
docker-compose logs -f lyrics-fetcher
docker-compose logs -f video-generator

# Access UIs
# MinIO Console: http://localhost:9001 (minioadmin/minioadmin)
# RabbitMQ Management: http://localhost:15672 (user/password)

# Storage locations:
# - shared/audio/ - Downloaded audio (temporary)
# - shared/audio_vocals/ - Separated vocals (temporary)
# - shared/audio_music/ - Instrumental tracks (temporary)
# - shared/lyrics/ - Synced lyrics (.lrc format)
# - MinIO bucket: karaoke-videos - Final videos (persistent)
# - MongoDB: karaoke.karaoke_entities - Video metadata (persistent)
```

## Services

### song-downloader
- Downloads YouTube audio with yt-dlp
- Sends audio to audio-separation service via RabbitMQ

### audio-separation
- Separates vocals/instrumental with audio-separator (MDX-Net model)
- Displays progress with custom loading bar
- Sends separated stems to lyrics-fetcher via RabbitMQ

### lyrics-fetcher
- Fetches synced lyrics from online sources (syncedlyrics)
- Exports to .lrc format
- Sends to video-generator via RabbitMQ

### video-generator
- Python-based using moviepy
- Creates karaoke-style videos with synchronized lyrics
- Shows upcoming lyric faded underneath current line
- Uses instrumental track for cleaner audio
- **Integrates shared storage library** to save videos directly to MinIO + MongoDB
- Uses `job_id` as primary identifier (simplified from separate karaoke_id)

## Tech Stack

- **Docker Compose** - Orchestration
- **RabbitMQ** - Message queue
- **MongoDB 8.0** - Document database
- **MinIO** - S3-compatible object storage
- **yt-dlp** - YouTube download
- **audio-separator** - Vocal separation (MDX-Net)
- **syncedlyrics** - Lyrics fetching
- **moviepy** - Video generation
- **Python 3.11** - All microservices
- **Shared Storage Library** - Reusable MongoDB + MinIO client (`shared/storage/`)

## Development

```bash
# Rebuild specific service
docker-compose build song-downloader

# View logs
docker-compose logs -f [service-name]

# Restart service
docker-compose restart [service-name]

# Stop all services
docker-compose down

# Clean up volumes (removes database and storage data)
docker-compose down -v
```

## Storage Access

### Shared Storage Library

The `shared/storage/` library provides a clean interface for storage operations:

```python
# Import the library
from storage import MinIOStorage, KaraokeRepository, KaraokeEntity, FileMeta, Ids, State

# Initialize MinIO
storage = MinIOStorage(
    endpoint='minio:9000',
    access_key='minioadmin',
    secret_key='minioadmin',
    bucket_name='karaoke-videos',
    secure=False
)

# Upload a file
object_name, size = storage.upload_file('video.mp4')

# Initialize MongoDB repository
from pymongo import MongoClient
mongo_client = MongoClient('mongodb://admin:password@mongodb:27017/')
repo = KaraokeRepository(mongo_client['karaoke']['karaoke_entities'])

# Create and save entity (note: no separate karaoke_id, just job_id)
entity = KaraokeEntity(
    job_id='unique-job-123',
    state=State.FINISHED,
    ids=Ids(youtube='video_id'),
    file_meta=FileMeta(
        file_uuid='uuid',
        bucket='karaoke-videos',
        object_name=object_name,
        file_name='video.mp4',
        file_size=size,
        mime_type='video/mp4'
    ),
    created_at=datetime.now(),
    updated_at=datetime.now()
)
repo.insert(entity)

# Query by job_id
entity = repo.find_by_job_id('unique-job-123')
```

### MongoDB

```bash
# Connect to MongoDB
mongosh mongodb://admin:password@localhost:27017/

# Query karaoke entities
use karaoke
db.karaoke_entities.find().pretty()
db.karaoke_entities.find({state: 'finished'})
db.karaoke_entities.findOne({job_id: 'your-job-id'})
```

### MinIO

```bash
# Access MinIO Console
open http://localhost:9001
# Login: minioadmin / minioadmin

# Or use MinIO client (mc)
mc alias set local http://localhost:9000 minioadmin minioadmin
mc ls local/karaoke-videos
mc cp local/karaoke-videos/video.mp4 ./downloads/
```

## Testing

```bash
# Run karaoke-storage tests
cd karaoke-storage
pip install -r requirements.txt
pip install pytest pytest-mock
pytest

# With coverage
pytest --cov=. --cov-report=html
open htmlcov/index.html
```
