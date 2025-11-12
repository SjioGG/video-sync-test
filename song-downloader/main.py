# song-downloader/main.py
import pika
import yt_dlp
import json
import os
import time
import logging
from threading import Thread

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'password')
OUTPUT_DIR = '/app/shared/audio'
DOWNLOAD_TIMEOUT = 90

os.makedirs(OUTPUT_DIR, exist_ok=True)


def download_song_worker(youtube_url, job_id):
    """Download audio from YouTube"""
    output_path = os.path.join(OUTPUT_DIR, f"{job_id}.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_path,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': False,
        'no_warnings': False,
        'noplaylist': True,
        'socket_timeout': 30,
        'retries': 3,
        'fragment_retries': 3,
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        logger.info(f"⬇️  Downloading: {youtube_url}")
        info = ydl.extract_info(youtube_url, download=True)
        
        return {
            'job_id': job_id,
            'title': info.get('title', 'Unknown'),
            'artist': info.get('artist', info.get('uploader', 'Unknown')),
            'duration': info.get('duration', 0),
            'audio_path': f"{OUTPUT_DIR}/{job_id}.mp3",
            'success': True
        }

def download_with_timeout(youtube_url, job_id, timeout):
    """Download with timeout wrapper"""
    result = {'success': False, 'error': 'Timeout'}
    exception = None
    
    def download_worker():
        nonlocal result, exception
        try:
            result = download_song_worker(youtube_url, job_id)
        except Exception as e:
            exception = e
            result = {'job_id': job_id, 'success': False, 'error': str(e)}
    
    thread = Thread(target=download_worker)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout)
    
    if thread.is_alive():
        return {'job_id': job_id, 'success': False, 'error': f'Timeout after {timeout}s'}
    
    if exception:
        raise exception
    
    return result

def process_audio(youtube_url, job_id):
    """Download audio from YouTube"""
    try:
        result = download_with_timeout(youtube_url, job_id, DOWNLOAD_TIMEOUT)
        
        if not result['success']:
            return result
        
        logger.info(f"✅ Downloaded: {result['title']}")
        
        return result
        
    except Exception as e:
        logger.error(f"❌ Processing failed: {e}")
        return {'job_id': job_id, 'success': False, 'error': str(e)}

def connect_rabbitmq():
    """Connect to RabbitMQ with retry"""
    max_retries = 10
    retry_delay = 5
    
    for attempt in range(max_retries):
        try:
            credentials = pika.PlainCredentials(RABBITMQ_USER, RABBITMQ_PASSWORD)
            parameters = pika.ConnectionParameters(
                host=RABBITMQ_HOST, port=RABBITMQ_PORT,
                credentials=credentials,
                heartbeat=600, blocked_connection_timeout=300
            )
            connection = pika.BlockingConnection(parameters)
            channel = connection.channel()
            
            channel.queue_declare(queue='song_requests', durable=True)
            channel.queue_declare(queue='separation_requests', durable=True)
            
            logger.info("✅ Connected to RabbitMQ")
            return connection, channel
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise

def callback(ch, method, properties, body):
    """Process audio requests"""
    try:
        message = json.loads(body)
        youtube_url = message['youtube_url']
        job_id = message['job_id']
        
        if not youtube_url.startswith('http'):
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        
        logger.info(f"🎵 Processing: {youtube_url}")
        
        result = process_audio(youtube_url, job_id)
        
        if result['success']:
            ch.basic_publish(
                exchange='', routing_key='separation_requests',
                body=json.dumps(result),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logger.info(f"📤 Sent to audio-separation: {job_id}")
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def main():
    logger.info("=" * 60)
    logger.info("🎵 Song Download Service")
    logger.info("   YouTube Audio Download with yt-dlp")
    logger.info("=" * 60)
    
    connection, channel = connect_rabbitmq()
    
    logger.info("=" * 60)
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='song_requests', on_message_callback=callback)
    
    logger.info('🚀 Ready! Waiting for download requests...')
    channel.start_consuming()

if __name__ == '__main__':
    main()
