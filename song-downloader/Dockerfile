# song-downloader/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies INCLUDING build tools for audio-separator
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    gcc \
    g++ \
    make \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies in order
RUN pip install --no-cache-dir pika==1.3.2

# Install latest yt-dlp from git
RUN pip install --no-cache-dir --upgrade git+https://github.com/yt-dlp/yt-dlp.git@master

# Install audio-separator with CPU support
RUN pip install --no-cache-dir "audio-separator[cpu]"

# Install gRPC
RUN pip install --no-cache-dir grpcio==1.60.0 grpcio-tools==1.60.0

# Copy proto file and generate gRPC code
COPY audio_enhancement.proto .
RUN python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    audio_enhancement.proto

COPY . .

CMD ["python", "main.py"]
