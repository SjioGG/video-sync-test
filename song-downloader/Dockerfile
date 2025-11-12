# song-downloader/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies
RUN pip install --no-cache-dir pika==1.3.2

# Install latest yt-dlp from git
RUN pip install --no-cache-dir --upgrade git+https://github.com/yt-dlp/yt-dlp.git@master

COPY . .

CMD ["python", "main.py"]
