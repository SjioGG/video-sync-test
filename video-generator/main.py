# video-generator/main.py
import pika
import json
import os
import logging
import sys
from datetime import datetime
from pathlib import Path
from moviepy.editor import (
    AudioFileClip, TextClip, CompositeVideoClip, ColorClip
)
from pymongo import MongoClient

# Import video-generator specific storage package
from storage import S3Client, KaraokeRepository, VideoStorageService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'password')
OUTPUT_DIR = '/app/shared/videos'

# Storage configuration
S3_ENDPOINT = os.getenv('S3_ENDPOINT', 'minio:9000')
S3_ACCESS_KEY = os.getenv('S3_ACCESS_KEY', 'minioadmin')
S3_SECRET_KEY = os.getenv('S3_SECRET_KEY', 'minioadmin')
S3_BUCKET = os.getenv('S3_BUCKET', 'karaoke-videos')
S3_SECURE = os.getenv('S3_SECURE', 'false').lower() == 'true'
MONGODB_URI = os.getenv('MONGODB_URI', 'mongodb://admin:password@mongodb:27017/')

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Global storage service
video_storage = None

def init_storage():
    """Initialize storage service (S3 + MongoDB)"""
    global video_storage
    
    try:
        logger.info(f"📦 Initializing storage...")
        logger.info(f"   S3 Endpoint: {S3_ENDPOINT}")
        logger.info(f"   S3 Bucket: {S3_BUCKET}")
        logger.info(f"   MongoDB: {MONGODB_URI}")
        
        # Initialize S3 client
        s3_client = S3Client(
            endpoint=S3_ENDPOINT,
            access_key=S3_ACCESS_KEY,
            secret_key=S3_SECRET_KEY,
            bucket_name=S3_BUCKET,
            secure=S3_SECURE
        )
        
        # Initialize MongoDB repository
        mongo_client = MongoClient(MONGODB_URI)
        db = mongo_client['karaoke']
        collection = db['karaoke_entities']
        repository = KaraokeRepository(collection)
        
        # Create storage service
        video_storage = VideoStorageService(s3_client, repository)
        
        logger.info("✅ Storage initialized")
    except Exception as e:
        logger.error(f"Failed to initialize storage: {e}")
        raise

class MoviePyProgressLogger:
    """Custom progress logger for MoviePy that integrates with our logging"""
    
    def __init__(self, logger):
        self.logger = logger
        self.last_logged_percent = -1
        
    def callback(self, **changes):
        """Called by moviepy during rendering"""
        if 't' in changes and 'duration' in changes:
            t = changes['t']
            duration = changes['duration']
            if duration > 0:
                progress = (t / duration) * 100
                # Log every 10%
                if int(progress) // 10 > self.last_logged_percent // 10:
                    self.logger.info(f"🎥 Rendering: {int(progress)}%")
                    self.last_logged_percent = int(progress)
    
    def bars_callback(self, bar, attr, value, old_value=None):
        """Alternative callback for progress bars"""
        if attr == 'index':
            percentage = (value / getattr(bar, 'total', 100)) * 100
            if int(percentage) // 10 > self.last_logged_percent // 10:
                self.logger.info(f"🎥 Rendering: {int(percentage)}%")
                self.last_logged_percent = int(percentage)

def parse_lrc(lrc_content):
    """Parse LRC format into list of {time, text}"""
    import re
    lines = lrc_content.split('\n')
    lyrics = []
    
    for line in lines:
        match = re.match(r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)', line)
        if match:
            minutes = int(match[1])
            seconds = int(match[2])
            milliseconds = int(match[3].ljust(3, '0'))
            text = match[4].strip()
            
            time_in_seconds = minutes * 60 + seconds + milliseconds / 1000
            
            if text:
                lyrics.append({
                    'time': time_in_seconds,
                    'text': text
                })
    
    return lyrics

def create_lyric_video(audio_path, lyrics_data, output_path, title, artist):
    """
    Generate karaoke-style video with synchronized lyrics
    """
    logger.info(f"🎬 Creating video with {len(lyrics_data)} lyric lines")
    
    # Load audio
    audio = AudioFileClip(audio_path)
    duration = audio.duration
    
    # Create black background
    background = ColorClip(size=(1920, 1080), color=(0, 0, 0), duration=duration)
    
    # Create lyric clips
    lyric_clips = []

    for i, lyric in enumerate(lyrics_data):
        start_time = lyric['time']
        end_time = lyrics_data[i + 1]['time'] if i + 1 < len(lyrics_data) else duration

        # If there's a next line, show it faded underneath during the current line
        if i + 1 < len(lyrics_data):
            next_text = lyrics_data[i + 1]['text']
            faded_clip = (TextClip(
                next_text,
                fontsize=50,
                color='white',
                font='DejaVu-Sans',
                size=(1720, None),
                method='caption',
                align='center'
            )
            .set_position(('center', 680))  # slightly lower than main line
            .set_start(start_time)
            .set_duration(end_time - start_time)
            .set_opacity(0.36)
            .crossfadein(0.2)
            .crossfadeout(0.2))

            # Add faded clip first so it's rendered under the main text
            lyric_clips.append(faded_clip)

        # Current lyric (on top)
        txt_clip = (TextClip(
            lyric['text'],
            fontsize=76,
            color='white',
            font='DejaVu-Sans-Bold',
            size=(1720, None),
            method='caption',
            align='center'
        )
        .set_position(('center', 520))
        .set_start(start_time)
        .set_duration(end_time - start_time)
        .crossfadein(0.25)
        .crossfadeout(0.25))

        lyric_clips.append(txt_clip)
    
    # Create title/artist text with simpler font
    title_clip = (TextClip(
        f"{title}\n{artist}",
        fontsize=32,
        color='gray',
        font='DejaVu-Sans',
        size=(1720, None),
        method='caption',
        align='center'
    )
    .set_position(('center', 900))
    .set_duration(duration))
    
    # Combine all clips
    video = CompositeVideoClip([background] + lyric_clips + [title_clip])
    video = video.set_audio(audio)
    
    # Create progress logger
    progress_logger = MoviePyProgressLogger(logger)
    
    # Render video with custom progress logging
    logger.info("🎥 Starting video render...")
    logger.info(f"   Duration: {duration:.1f}s, FPS: 30, Resolution: 1920x1080")
    
    try:
        video.write_videofile(
            output_path,
            fps=30,
            codec='libx264',
            audio_codec='aac',
            audio_bitrate='320k',
            preset='medium',
            threads=4,
            logger='bar',  # Use progress bar
            verbose=False  # Reduce ffmpeg output
        )
    except Exception as e:
        # If progress logging fails, fall back to simple mode
        logger.warning("Progress logging unavailable, using simple mode")
        video.write_videofile(
            output_path,
            fps=30,
            codec='libx264',
            audio_codec='aac',
            audio_bitrate='320k',
            preset='medium',
            threads=4,
            logger=None
        )
    
    logger.info(f"✅ Video saved: {output_path}")
    
    # Clean up
    video.close()
    audio.close()

def process_video_request(message):
    """Process video generation request"""
    try:
        job_id = message['job_id']
        title = message['title']
        artist = message['artist']
        youtube_id = message.get('youtube_id')
        audio_path = message.get('music_path') or message.get('audio_path')
        lyrics_path = message['lyrics_path']
        
        logger.info(f"🎬 Processing video for job {job_id}: {title} by {artist}")
        
        # Read lyrics
        with open(lyrics_path, 'r', encoding='utf-8') as f:
            lyrics_content = f.read()
        
        lyrics_data = parse_lrc(lyrics_content)
        
        if not lyrics_data:
            logger.error("No valid lyrics found")
            return {'success': False, 'error': 'No lyrics'}
        
        logger.info(f"Found {len(lyrics_data)} lyric lines")
        
        # Generate video
        output_path = os.path.join(OUTPUT_DIR, f"{job_id}.mp4")
        create_lyric_video(audio_path, lyrics_data, output_path, title, artist)
        
        logger.info(f"✅ Video generation complete: {output_path}")
        
        # Save to storage (S3 + MongoDB)
        if video_storage:
            video_storage.save_video(
                job_id=job_id,
                video_path=output_path,
                youtube_id=youtube_id,
                cleanup_local=True
            )
        else:
            logger.warning("⚠️  Storage not initialized, skipping save")
        
        return {'success': True, 'video_path': output_path}
        
    except Exception as e:
        logger.error(f"❌ Error generating video: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'success': False, 'error': str(e)}

def connect_rabbitmq():
    """Connect to RabbitMQ with retry"""
    max_retries = 10
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST,
                port=RABBITMQ_PORT,
                credentials=credentials,
                heartbeat=600,
                blocked_connection_timeout=300
            )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            
            channel.queue_declare(queue='video_requests', durable=True)
            
            logger.info("✅ Connected to RabbitMQ")
            return connection, channel
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
            else:
                raise

def callback(ch, method, properties, body):
    """Process video requests"""
    try:
        message = json.loads(body)
        result = process_video_request(message)
        
        if result['success']:
            logger.info(f"✅ Success: {message['job_id']}")
        else:
            logger.error(f"❌ Failed: {result.get('error')}")
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def main():
    logger.info("=" * 60)
    logger.info("🎬 Video Generator Service")
    logger.info("   Python + MoviePy + Storage")
    logger.info("=" * 60)
    
    # Initialize storage
    init_storage()
    
    connection, channel = connect_rabbitmq()
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='video_requests', on_message_callback=callback)
    
    logger.info('🚀 Ready! Waiting for messages...')
    channel.start_consuming()

if __name__ == '__main__':
    main()
