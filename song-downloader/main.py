# song-downloader/main.py
import pika
import yt_dlp
import json
import os
import time
import logging
import shutil
import grpc
from threading import Thread
from audio_separator.separator import Separator
import audio_enhancement_pb2
import audio_enhancement_pb2_grpc

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RABBITMQ_HOST = os.getenv('RABBITMQ_HOST', 'localhost')
RABBITMQ_PORT = int(os.getenv('RABBITMQ_PORT', 5672))
RABBITMQ_USER = os.getenv('RABBITMQ_USER', 'user')
RABBITMQ_PASSWORD = os.getenv('RABBITMQ_PASSWORD', 'password')
ENHANCEMENT_HOST = os.getenv('ENHANCEMENT_HOST', 'speech-enhancement')
ENHANCEMENT_PORT = int(os.getenv('ENHANCEMENT_PORT', 50051))
OUTPUT_DIR = '/app/shared/audio'
OUTPUT_DIR_VOCALS = '/app/shared/audio_vocals'
OUTPUT_DIR_MUSIC = '/app/shared/audio_music'
DOWNLOAD_TIMEOUT = 90

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR_VOCALS, exist_ok=True)
os.makedirs(OUTPUT_DIR_MUSIC, exist_ok=True)

separator = None

def init_separator():
    """Initialize audio-separator with faster model"""
    global separator
    
    logger.info("🎛️  Initializing audio-separator...")
    separator = Separator(
        log_level=logging.INFO,
        model_file_dir='/app/shared/models',
        output_dir=OUTPUT_DIR,
        output_format='WAV',
        mdxc_params={
            'segment_size': 128,
            'batch_size': 2,
            'overlap': 4
        }
    )
    
    logger.info("📥 Loading MDX-Net Inst HQ model (fast, high quality)...")
    separator.load_model(model_filename='UVR-MDX-NET-Inst_HQ_3.onnx')
    logger.info("✅ Model loaded!")

def enhance_vocals_with_grpc(input_wav: str, output_wav: str) -> str:
    """Enhance vocals using speech-enhancement service via gRPC"""
    try:
        logger.info(f"🎤 Calling enhancement service for: {input_wav}")
        
        # Create gRPC channel
        channel = grpc.insecure_channel(f'{ENHANCEMENT_HOST}:{ENHANCEMENT_PORT}')
        stub = audio_enhancement_pb2_grpc.AudioEnhancerStub(channel)
        
        # Make RPC call with timeout
        request = audio_enhancement_pb2.EnhanceRequest(
            input_path=input_wav,
            output_path=output_wav
        )
        
        response = stub.EnhanceAudio(request, timeout=60.0)
        
        channel.close()
        
        if response.success:
            logger.info(f"✅ Enhancement complete: {response.output_path}")
            return response.output_path
        else:
            logger.error(f"❌ Enhancement failed: {response.error}")
            logger.warning("⚠️  Using unenhanced vocals")
            return input_wav
            
    except grpc.RpcError as e:
        logger.error(f"❌ gRPC error: {e.code()} - {e.details()}")
        logger.warning("⚠️  Using unenhanced vocals")
        return input_wav
    except Exception as e:
        logger.error(f"❌ Enhancement error: {e}")
        logger.warning("⚠️  Using unenhanced vocals")
        return input_wav

def separate_vocals(audio_path, job_id):
    """Separate vocals using audio-separator and enhance via gRPC"""
    try:
        logger.info(f"🎵 Separating vocals: {audio_path}")
        logger.info("   (This may take 2-5 minutes on CPU...)")
        
        start_time = time.time()
        output_files = separator.separate(audio_path)
        duration = time.time() - start_time
        
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
        
        # Move music file
        shutil.move(music_file, music_path)
        logger.info(f"✅ Music: {music_path}")
        
        # Enhance vocals via gRPC call to speech-enhancement service
        temp_vocals = vocals_file
        enhanced_vocals = enhance_vocals_with_grpc(temp_vocals, vocals_path)
        
        # Remove the temporary unenhanced vocals if different from final
        if temp_vocals != enhanced_vocals and os.path.exists(temp_vocals):
            os.remove(temp_vocals)
        
        logger.info(f"✅ Enhanced vocals: {vocals_path}")
        
        return {
            'success': True,
            'vocals_path': vocals_path,
            'music_path': music_path
        }
        
    except Exception as e:
        logger.error(f"❌ Separation error: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return {'success': False, 'error': str(e)}


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
    """Download + Separate"""
    try:
        result = download_with_timeout(youtube_url, job_id, DOWNLOAD_TIMEOUT)
        
        if not result['success']:
            return result
        
        logger.info(f"✅ Downloaded: {result['title']}")
        
        separation_result = separate_vocals(result['audio_path'], job_id)
        
        if separation_result['success']:
            result['vocals_path'] = separation_result['vocals_path']
            result['music_path'] = separation_result['music_path']
        else:
            logger.warning("⚠️  Separation failed, using original")
            result['vocals_path'] = result['audio_path']
        
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
                exchange='', routing_key='lyrics_requests',
                body=json.dumps(result),
                properties=pika.BasicProperties(delivery_mode=2)
            )
            logger.info(f"📤 Sent to lyrics: {job_id}")
        
        ch.basic_ack(delivery_tag=method.delivery_tag)
        
    except Exception as e:
        logger.error(f"Error: {e}")
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)

def main():
    logger.info("=" * 60)
    logger.info("🎵 Audio Processing Service")
    logger.info("   YouTube Download + MDX-Net Vocal Separation")
    logger.info("   + gRPC Speech Enhancement")
    logger.info("=" * 60)
    
    connection, channel = connect_rabbitmq()
    init_separator()
    
    logger.info("=" * 60)
    
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='song_requests', on_message_callback=callback)
    
    logger.info('🚀 Ready!')
    channel.start_consuming()

if __name__ == '__main__':
    main()
