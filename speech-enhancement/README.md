# Speech Enhancement Service - gRPC Integration

## Overview
Separate microservice that handles vocal enhancement using DeepFilterNet, communicating with the song-downloader service via gRPC.

## Architecture

```
┌─────────────────────┐       gRPC        ┌──────────────────────┐
│  song-downloader    │ ──────────────>  │ speech-enhancement   │
│  (audio-separator)  │  EnhanceAudio()  │  (DeepFilterNet)     │
└─────────────────────┘                   └──────────────────────┘
         │                                          │
         └────────────── shared volume ────────────┘
                    /app/shared/audio_vocals/
```

## Services

### speech-enhancement
- **Port**: 50051 (gRPC)
- **Technology**: Python 3.10, DeepFilterNet, gRPC
- **Purpose**: Enhance separated vocals to improve transcription quality
- **Dependencies**: torch 2.2.0, torchaudio 2.2.0, deepfilternet 0.5.6

### song-downloader (updated)
- **Client**: Calls speech-enhancement via gRPC
- **Technology**: Python 3.11, audio-separator, gRPC client
- **Flow**: 
  1. Download YouTube audio
  2. Separate vocals/instrumental with MDX-Net
  3. Call gRPC service to enhance vocals
  4. Pass enhanced vocals to lyrics-fetcher

## Files Created

- `speech-enhancement/Dockerfile` - Service container definition
- `speech-enhancement/main.py` - gRPC server with DeepFilterNet
- `speech-enhancement/requirements.txt` - Python dependencies
- `speech-enhancement/audio_enhancement.proto` - gRPC service definition
- `song-downloader/audio_enhancement.proto` - gRPC client definition (copied)

## Docker Compose Changes

Added `speech-enhancement` service with:
- Shared volumes for audio files
- Network connectivity to app-network
- Dependency from song-downloader

## Testing

To test the system:

```bash
# Start all services
docker-compose up -d

# Check logs
docker logs video-sync-test-speech-enhancement-1
docker logs video-sync-test-song-downloader-1

# Send a test job (from song-downloader directory)
uv run producer.py
```

## Benefits of gRPC Separation

1. **Dependency Isolation**: DeepFilterNet's torch/torchaudio dependencies don't conflict with audio-separator
2. **Independent Scaling**: Can scale enhancement service separately
3. **Maintainability**: Easier to update/replace enhancement model
4. **Resilience**: If enhancement fails, vocals still processed (degraded mode)
5. **Technology Flexibility**: Services can use different Python versions (3.10 vs 3.11)
