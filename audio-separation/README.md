# Audio Separation Service

Dedicated microservice for audio stem separation using MDX-Net.

## Features

- **MDX-Net Model**: High-quality vocal/instrumental separation
- **Loading Bar**: Visual progress indicator for separation operations
- **RabbitMQ Integration**: Receives jobs from song-downloader, sends results to lyrics-fetcher
- **Modular Design**: Clean separation of concerns with `loading_bar.py` utility

## Architecture

```
song-downloader → [separation_requests queue]
                         ↓
                  audio-separation
                         ↓
                  [lyrics_requests queue] → lyrics-fetcher
```

## Files

- `main.py` - Main service with RabbitMQ consumer and separation logic
- `loading_bar.py` - Reusable progress bar utility for clear logging
- `Dockerfile` - Container with audio-separator[cpu] and dependencies
- `requirements.txt` - Python dependencies (pika)

## Environment Variables

- `RABBITMQ_HOST` - RabbitMQ hostname (default: localhost)
- `RABBITMQ_PORT` - RabbitMQ port (default: 5672)
- `RABBITMQ_USER` - RabbitMQ username (default: user)
- `RABBITMQ_PASSWORD` - RabbitMQ password (default: password)

## Usage

Receives messages from `separation_requests` queue with format:
```json
{
  "job_id": "uuid",
  "audio_path": "/app/shared/audio/uuid.mp3",
  "title": "Song Title",
  "artist": "Artist Name"
}
```

Outputs separated files to:
- `/app/shared/audio_vocals/{job_id}_vocals.wav`
- `/app/shared/audio_music/{job_id}_music.wav`

Then forwards to lyrics service with all metadata included.
