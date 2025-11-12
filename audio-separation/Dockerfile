# audio-separation/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for audio-separator
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    gcc \
    g++ \
    make \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Install pika first
RUN pip install --no-cache-dir pika==1.3.2

# Install audio-separator with CPU support
RUN pip install --no-cache-dir "audio-separator[cpu]"

COPY . .

CMD ["python", "main.py"]
