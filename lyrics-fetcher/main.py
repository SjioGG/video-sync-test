# lyrics-fetcher/main.py
import warnings
warnings.filterwarnings('ignore', category=UserWarning)
warnings.filterwarnings('ignore', category=FutureWarning)

import pika
import json
import os
import time
import logging
from fetcher import fetch_synced_lyrics
from transcriber import transcribe_audio_with_whisper
from aligner import align_words_with_whisper, export_word_level_lrc, export_word_timestamps_json

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
WHISPER_MODEL = os.getenv('WHISPER_MODEL', 'small.en')

os.makedirs(OUTPUT_DIR, exist_ok=True)

def process_lyrics(title, artist, audio_path, job_id):
    """
    Process lyrics with word-level alignment, initial prompt, and transparent diagnostics.
    """
    try:
        logger.info(f"📝 Processing lyrics for: {title} by {artist}")

        # Step 1: Fetch lyrics
        fetched_lyrics = fetch_synced_lyrics(title, artist)
        if not fetched_lyrics:
            logger.warning("No synced lyrics found")
        
        # Build CLEAN prompt (Whisper has ~50 token limit for initial_prompt)
        if fetched_lyrics:
            # Extract ONLY text, no timestamps
            lines = [line['text'].strip() for line in fetched_lyrics if line.get('text')]
            # Join with spaces
            prompt_text = " ".join(lines)
            # Truncate if too long (max ~220 chars = ~50 tokens)
            original_len = len(prompt_text)
            if len(prompt_text) > 220:
                prompt_text = prompt_text[:220].rsplit(' ', 1)[0]  # Cut at word boundary
                logger.info(f"Truncated prompt from {original_len} to {len(prompt_text)} chars")
        else:
            prompt_text = ""
        
        if prompt_text:
            logger.info(f"Using initial_prompt for Whisper (len={len(prompt_text)} chars)")
            logger.info(f"   Prompt preview: {prompt_text[:80]}...")

        # Step 2: Transcribe with Whisper using SHORT prompt
        transcription_start = time.time()
        whisper_transcription = transcribe_audio_with_whisper(
            audio_path,  # This should be vocals_path from callback
            WHISPER_MODEL,
            initial_prompt="lyrics"
        )
        transcription_end = time.time()
        total_transcribe_time = transcription_end - transcription_start
        logger.info(f"Whisper transcription finished in {total_transcribe_time:.2f}s")
        
        if not whisper_transcription:
            logger.error("No Whisper transcription available")
            return {'success': False, 'error': 'No Whisper transcription'}

        # Step 3: Align at WORD level (use improved algorithm if available)
        aligned_words = align_words_with_whisper(fetched_lyrics, whisper_transcription)
        if not aligned_words:
            logger.error("No word-level alignment produced")
            return {'success': False, 'error': 'No words aligned'}
        
        # Step 4: Export both formats
        lyrics_path = os.path.join(OUTPUT_DIR, f"{job_id}.lrc")
        lrc_export_ok = export_word_level_lrc(aligned_words, lyrics_path)
        if not lrc_export_ok:
            logger.warning("Failed to export LRC file")

        json_path = export_word_timestamps_json(aligned_words, lyrics_path)
        if not json_path:
            logger.warning("Failed to export JSON file")

        avg_confidence = sum(w['confidence'] for w in aligned_words) / len(aligned_words)
        lines_conf = f"   Words: {len(aligned_words)}\n   Avg confidence: {avg_confidence:.2f}"
        logger.info(f"✅ Word-level alignment complete!\n{lines_conf}")

        # Diagnostics for debugging and post-mortem
        try:
            conf_bad = [w for w in aligned_words if w['confidence'] < 0.5]
            if len(conf_bad) > 0:
                logger.info(f"   Warning: {len(conf_bad)} words below 0.5 confidence (first: {conf_bad[:10]})")
            # Optional: log first timings to verify offset problems
            if len(aligned_words) > 0:
                first_line = aligned_words[:10]
                logger.info("   First 10 aligned words:\n" +
                            "\n".join([f"[{w['start']:.2f}s -> {w['end']:.2f}s] {w['word']} (conf={w['confidence']:.2f})"
                                       for w in first_line]))
        except Exception as e:
            logger.warning(f"Diagnostics error: {e}")

        return {
            'success': True,
            'lyrics_path': lyrics_path,
            'words_json_path': json_path,
            'has_sync': True,
            'word_count': len(aligned_words),
            'avg_confidence': avg_confidence,
            'source': 'word_level'
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
        vocals_path = message.get('vocals_path', audio_path)  # Use vocals if available
        
        logger.info(f"🎵 Processing job {job_id}: {title} by {artist}")
        
        result = process_lyrics(title, artist, vocals_path, job_id)
        
        if result['success']:
            logger.info(f"✅ Word-level lyrics ready: {job_id}")
            
            video_message = {
                'job_id': job_id,
                'title': title,
                'artist': artist,
                'audio_path': audio_path,
                'lyrics_path': result['lyrics_path'],
                'words_json_path': result.get('words_json_path'),
                'has_sync': result['has_sync'],
                'lyrics_quality': {
                    'word_count': result.get('word_count', 0),
                    'avg_confidence': result.get('avg_confidence', 0),
                    'source': result.get('source', 'unknown')
                }
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
    logger.info("🎵 Lyrics Service Starting...")
    logger.info(f"   Whisper Model: {WHISPER_MODEL}")
    logger.info("   Features:")
    logger.info("   ✓ Word-level timestamps (Whisper)")
    logger.info("   ✓ Accurate text (syncedlyrics)")
    logger.info("   ✓ Intelligent word alignment")
    logger.info("=" * 60)
    
    connection, channel = connect_rabbitmq()
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='lyrics_requests', on_message_callback=callback)
    
    logger.info('🚀 Lyrics Service started. Waiting for messages...')
    channel.start_consuming()

if __name__ == '__main__':
    main()
