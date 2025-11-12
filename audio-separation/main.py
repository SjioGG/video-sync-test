# audio-separation/main.py
import pika
import json
import os
import time
import logging
import shutil
from audio_separator.separator import Separator
from loading_bar import LoadingBar

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'password')
INPUT_DIR = '/app/shared/audio'
OUTPUT_DIR = '/app/shared/audio'
OUTPUT_DIR_VOCALS = '/app/shared/audio_vocals'
OUTPUT_DIR_MUSIC = '/app/shared/audio_music'

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR_VOCALS, exist_ok=True)
os.makedirs(OUTPUT_DIR_MUSIC, exist_ok=True)

separator = None

def init_separator():
    """Initialize audio-separator with MDX-Net model"""
    global separator
    
    logger.info("=" * 60)
    logger.info("🎛️  Initializing Audio Separator")
    logger.info("=" * 60)
    
    separator = Separator(
        log_level=logging.WARNING,  # Reduce separator's own logs
        model_file_dir='/app/shared/models',
        output_dir=OUTPUT_DIR,
        output_format='WAV',
        mdxc_params={
            'segment_size': 128,
            'batch_size': 2,
            'overlap': 4
        }
    )
    
    logger.info("📥 Loading MDX-Net Inst HQ model...")
    separator.load_model(model_filename='UVR-MDX-NET-Inst_HQ_3.onnx')
    logger.info("✅ Model loaded and ready!")
    logger.info("=" * 60)

def separate_audio(audio_path, job_id):
    """
    Separate vocals and instrumental from audio file
    Returns paths to separated files
    """
    try:
        logger.info(f"🎵 Separating audio: {os.path.basename(audio_path)}")
        logger.info(f"   Job ID: {job_id}")
        logger.info("   (This may take 2-5 minutes on CPU...)")
        
        # Create and start activity indicator
        loading_bar = LoadingBar(description="Audio Separation")
        loading_bar.start()
        
        start_time = time.time()
        output_files = separator.separate(audio_path)
        duration = time.time() - start_time
        
        loading_bar.stop()
        
        logger.info(f"✅ Separation complete in {duration:.1f}s!")
        logger.info(f"   Output files: {output_files}")
        
        vocals_file = None
        music_file = None
        
        # Files are returned as relative names, need to prepend OUTPUT_DIR
        for file in output_files:
            full_path = os.path.join(OUTPUT_DIR, file) if not file.startswith('/') else file
            
            if '(Vocals)' in file or 'vocals' in file.lower():
                vocals_file = full_path
            elif '(Instrumental)' in file or 'instrumental' in file.lower():
                music_file = full_path
        
        if not vocals_file or not music_file:
            raise Exception(f"Could not find vocal/instrumental files in: {output_files}")
        
        # Verify files exist
        if not os.path.exists(vocals_file):
            raise Exception(f"Vocals file not found: {vocals_file}")
        if not os.path.exists(music_file):
            raise Exception(f"Music file not found: {music_file}")
        
        vocals_path = os.path.join(OUTPUT_DIR_VOCALS, f"{job_id}_vocals.wav")
        music_path = os.path.join(OUTPUT_DIR_MUSIC, f"{job_id}_music.wav")
        
        # Move files to final locations
        shutil.move(vocals_file, vocals_path)
        shutil.move(music_file, music_path)
        
        loading_bar.complete()
        
        logger.info(f"✅ Vocals: {vocals_path}")
        logger.info(f"✅ Music: {music_path}")
        
        return {
            'success': True,
            'vocals_path': vocals_path,
            'music_path': music_path,
            'duration': duration
        }
        
    except Exception as e:
        logger.error(f"❌ Separation error: {e}")
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
            
            channel.queue_declare(queue='separation_requests', durable=True)
            channel.queue_declare(queue='lyrics_requests', durable=True)
            
            logger.info("✅ Connected to RabbitMQ")
            return connection, channel
        except Exception as e:
            logger.warning(f"Attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            else:
                raise

def callback(ch, method, properties, body):
    """Process separation requests"""
    try:
        message = json.loads(body)
        job_id = message['job_id']
        audio_path = message['audio_path']
        
        logger.info(f"📥 Received separation request: {job_id}")
        
        result = separate_audio(audio_path, job_id)
        
        if result['success']:
            # Forward to lyrics service with all data
            lyrics_message = {
                'job_id': job_id,
                'title': message.get('title', 'Unknown'),
                'artist': message.get('artist', 'Unknown'),
                'audio_path': audio_path,
                'vocals_path': result['vocals_path'],
                'music_path': result['music_path']
            }
            
            ch.basic_publish(
                exchange='',
                routing_key='lyrics_requests',
                body=json.dumps(lyrics_message),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logger.info(f"📤 Sent to lyrics service: {job_id}")
        else:
            logger.error(f"❌ Separation failed for {job_id}: {result.get('error')}")
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        import traceback
        logger.error(traceback.format_exc())
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def main():
    logger.info("=" * 60)
    logger.info("🎛️  Audio Separation Service")
    logger.info("   MDX-Net Vocal/Instrumental Separation")
    logger.info("=" * 60)
    
    connection, channel = connect_rabbitmq()
    init_separator()
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='separation_requests', on_message_callback=callback)
    
    logger.info('🚀 Ready! Waiting for separation requests...')
    channel.start_consuming()

if __name__ == '__main__':
    main()
