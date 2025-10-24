# lyrics-fetcher/main.py
import pika
import syncedlyrics
import json
import os
import time
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'password')
OUTPUT_DIR = '/app/shared/lyrics'

os.makedirs(OUTPUT_DIR, exist_ok=True)

def fetch_lyrics(title, artist, job_id):
    """Fetch synchronized lyrics using syncedlyrics"""
    try:
        # Clean up title - remove extra text like "(Official Video)" etc
        clean_title = title
        for suffix in ['(Official Video)', '(Official Music Video)', '(4K Remaster)', 
                       '[Official Video]', '[Official Music Video]', '(Lyric Video)',
                       '(Audio)', '[Audio]', '(Lyrics)', '[Lyrics]']:
            clean_title = clean_title.replace(suffix, '').strip()
        
        # Build search term - just artist and song title
        search_term = f"{artist} {clean_title}"
        logger.info(f"Searching lyrics for: {search_term}")
        
        # Simple search - syncedlyrics automatically tries synced first
        lrc = syncedlyrics.search(search_term)
        
        if lrc:
            lyrics_path = os.path.join(OUTPUT_DIR, f"{job_id}.lrc")
            with open(lyrics_path, 'w', encoding='utf-8') as f:
                f.write(lrc)
            
            # Check if lyrics are time-synced (contains timestamps)
            has_sync = '[' in lrc and ']' in lrc and ':' in lrc
            
            logger.info(f"Found lyrics (synced: {has_sync})")
            
            return {
                'success': True,
                'lyrics_path': lyrics_path,
                'has_sync': has_sync
            }
        else:
            logger.warning(f"No lyrics found for: {search_term}")
            return {
                'success': False,
                'error': 'No lyrics found'
            }
            
    except Exception as e:
        logger.error(f"Error fetching lyrics: {e}")
        return {
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
            
            # Declare queues
            channel.queue_declare(queue='lyrics_requests', durable=True)
            channel.queue_declare(queue='video_requests', durable=True)
            
            logger.info("Connected to RabbitMQ")
            return connection, channel
        except Exception as e:
            logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise

def callback(ch, method, properties, body):
    """Process incoming lyrics fetch requests"""
    try:
        message = json.loads(body)
        job_id = message['job_id']
        title = message['title']
        artist = message['artist']
        audio_path = message['audio_path']
        
        logger.info(f"Fetching lyrics for job {job_id}: {title} by {artist}")
        
        # Fetch lyrics
        result = fetch_lyrics(title, artist, job_id)
        
        if result['success']:
            logger.info(f"Successfully fetched lyrics: {job_id}")
            
            # Prepare message for video generator
            video_message = {
                'job_id': job_id,
                'title': title,
                'artist': artist,
                'audio_path': audio_path,
                'lyrics_path': result['lyrics_path'],
                'has_sync': result['has_sync']
            }
            
            # Send to video generator
            ch.basic_publish(
                exchange='',
                routing_key='video_requests',
                body=json.dumps(video_message),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logger.info(f"Sent to video generator: {job_id}")
        else:
            logger.error(f"Failed to fetch lyrics: {result.get('error')}")
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def main():
    connection, channel = connect_rabbitmq()
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='lyrics_requests', on_message_callback=callback)
    
    logger.info('Lyrics Fetcher Service started. Waiting for messages...')
    channel.start_consuming()

if __name__ == '__main__':
    main()
