# video-generator/Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for moviepy
RUN apt-get update && apt-get install -y \
    ffmpeg \
    imagemagick \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Fix ImageMagick policy to allow text operations
RUN find /etc -name policy.xml -exec sed -i \
    -e '/<policy domain="path" rights="none" pattern="@\*"/d' \
    -e 's/<policy domain="coder" rights="none" pattern="TEXT" \/>/<policy domain="coder" rights="read|write" pattern="TEXT" \/>/g' \
    -e 's/<policy domain="coder" rights="none" pattern="LABEL" \/>/<policy domain="coder" rights="read|write" pattern="LABEL" \/>/g' \
    {} \;

# Copy service files
COPY video-generator/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy storage package
COPY video-generator/storage /app/storage

# Copy main application
COPY video-generator/*.py /app/

CMD ["python", "main.py"]
