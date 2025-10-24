# song-downloader/main.py
import pika
import yt_dlp
import json
import os
import time
import logging
from threading import Thread, Event

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'password')
OUTPUT_DIR = '/app/shared/audio'
DOWNLOAD_TIMEOUT = 90  # 90 seconds timeout

os.makedirs(OUTPUT_DIR, exist_ok=True)

class TimeoutError(Exception):
    pass

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
            result = {
                'job_id': job_id,
                'success': False,
                'error': str(e)
            }
    
    thread = Thread(target=download_worker)
    thread.daemon = True
    thread.start()
    thread.join(timeout=timeout)
    
    if thread.is_alive():
        logger.error(f"Download timeout after {timeout}s - YouTube may be blocking")
        return {
            'job_id': job_id,
            'success': False,
            'error': f'Download timeout after {timeout}s'
        }
    
    if exception:
        raise exception
    
    return result

def download_song_worker(youtube_url, job_id):
    """Actual download logic"""
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
        logger.info(f"Downloading: {youtube_url}")
        info = ydl.extract_info(youtube_url, download=True)
        
        return {
            'job_id': job_id,
            'title': info.get('title', 'Unknown'),
            'artist': info.get('artist', info.get('uploader', 'Unknown')),
            'duration': info.get('duration', 0),
            'audio_path': f"{OUTPUT_DIR}/{job_id}.mp3",
            'success': True
        }

def download_song(youtube_url, job_id):
    """Download with timeout protection"""
    try:
        return download_with_timeout(youtube_url, job_id, DOWNLOAD_TIMEOUT)
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return {
            'job_id': job_id,
            'success': False,
            'error': str(e)
        }

def connect_rabbitmq():
    """Connect to RabbitMQ with retry logic"""
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
            
            channel.queue_declare(queue='song_requests', durable=True)
            channel.queue_declare(queue='lyrics_requests', durable=True)
            
            logger.info("Connected to RabbitMQ")
            return connection, channel
        except Exception as e:
            logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise

def callback(ch, method, properties, body):
    """Process incoming song download requests"""
    try:
        message = json.loads(body)
        youtube_url = message['youtube_url']
        job_id = message['job_id']
        
        if not youtube_url.startswith('http'):
            logger.error(f"Invalid URL: {youtube_url}")
            ch.basic_ack(delivery_tag=method.delivery_tag)
            return
        
        logger.info(f"Processing job {job_id}: {youtube_url}")
        
        result = download_song(youtube_url, job_id)
        
        if result['success']:
            logger.info(f"Successfully downloaded: {result['title']}")
            
            ch.basic_publish(
                exchange='',
                routing_key='lyrics_requests',
                body=json.dumps(result),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logger.info(f"Sent to lyrics fetcher: {job_id}")
        else:
            logger.error(f"Failed to download: {result.get('error')}")
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def main():
    logger.info("=" * 60)
    logger.info("Song Downloader Service starting...")
    logger.info("Using yt-dlp (latest nightly)")
    logger.info("Note: YouTube currently blocking downloaders (Oct 23, 2025)")
    logger.info("Service will timeout gracefully and wait for yt-dlp fix")
    logger.info("=" * 60)
    
    connection, channel = connect_rabbitmq()
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='song_requests', on_message_callback=callback)
    
    logger.info('Song Downloader Service started. Waiting for messages...')
    channel.start_consuming()

if __name__ == '__main__':
    main()
