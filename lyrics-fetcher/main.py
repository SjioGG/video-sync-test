# lyrics-fetcher/main.py
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

import pika
import json
import os
import logging
from fetcher import fetch_synced_lyrics

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'password')
OUTPUT_DIR = '/app/shared/lyrics'

os.makedirs(OUTPUT_DIR, exist_ok=True)

def process_lyrics(title, artist, job_id):
    """
    Fetch synced lyrics from online sources
    """
    try:
        logger.info(f"📝 Fetching lyrics for: {title} by {artist}")

        # Fetch lyrics
        lyrics = fetch_synced_lyrics(title, artist)
        if not lyrics:
            logger.warning("No synced lyrics found")
            return {'success': False, 'error': 'No lyrics found'}
        
        logger.info(f"✅ Found {len(lyrics)} lyric lines")
        
        # Export to LRC format
        lyrics_path = os.path.join(OUTPUT_DIR, f"{job_id}.lrc")
        with open(lyrics_path, 'w', encoding='utf-8') as f:
            for line in lyrics:
                minutes = int(line['time'] // 60)
                seconds = line['time'] % 60
                f.write(f"[{minutes:02d}:{seconds:05.2f}]{line['text']}\n")
        
        logger.info(f"✅ Lyrics saved: {lyrics_path}")

        return {
            'success': True,
            'lyrics_path': lyrics_path,
            'has_sync': True,
            'line_count': len(lyrics),
            'source': 'online'
        }

    except Exception as e:
        logger.error(f"Error processing lyrics: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'success': False, 'error': str(e)}

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
            
            channel.queue_declare(queue='lyrics_requests', durable=True)
            channel.queue_declare(queue='video_requests', durable=True)
            
            logger.info("Connected to RabbitMQ")
            return connection, channel
        except Exception as e:
            logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
            else:
                raise

def callback(ch, method, properties, body):
    """Process incoming lyrics requests"""
    try:
        message = json.loads(body)
        job_id = message['job_id']
        title = message['title']
        artist = message['artist']
        audio_path = message['audio_path']
        
        logger.info(f"🎵 Processing job {job_id}: {title} by {artist}")
        
        result = process_lyrics(title, artist, job_id)
        
        if result['success']:
            logger.info(f"✅ Lyrics ready: {job_id}")
            
            video_message = {
                'job_id': job_id,
                'title': title,
                'artist': artist,
                'audio_path': audio_path,
                'vocals_path': message.get('vocals_path', audio_path),
                'music_path': message.get('music_path', ''),
                'lyrics_path': result['lyrics_path'],
                'has_sync': result['has_sync']
            }
            
            ch.basic_publish(
                exchange='',
                routing_key='video_requests',
                body=json.dumps(video_message),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logger.info(f"📤 Sent to video generator: {job_id}")
        else:
            logger.error(f"❌ Failed: {result.get('error')}")
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def main():
    logger.info("=" * 60)
    logger.info("🎵 Lyrics Service")
    logger.info("   Fetching synced lyrics from online sources")
    logger.info("=" * 60)
    
    connection, channel = connect_rabbitmq()
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='lyrics_requests', on_message_callback=callback)
    
    logger.info('🚀 Ready! Waiting for messages...')
    channel.start_consuming()

if __name__ == '__main__':
    main()
