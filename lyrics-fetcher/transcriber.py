# lyrics-fetcher/transcriber.py
import whisper
import logging
import time

logger = logging.getLogger(__name__)

def transcribe_audio_with_whisper(audio_path, model_name='small.en', initial_prompt=""):
    """
    Optimized Whisper transcription with optional prompt
    """
    try:
        logger.info(f"Loading Whisper model: {model_name}")
        model_load_start = time.time()
        model = whisper.load_model(model_name)
        model_load_time = time.time() - model_load_start
        logger.info(f"   Model loaded in {model_load_time:.1f}s")
        
        logger.info(f"Transcribing: {audio_path}")
        if initial_prompt:
            logger.info(f"   Using initial prompt (length: {len(initial_prompt)} chars)")
        
        transcribe_start = time.time()
        
        result = model.transcribe(
            audio_path,
            language='en',
            word_timestamps=True,
            task='transcribe',
            initial_prompt=initial_prompt,  # ← ADD THIS
            
            # Rest of your settings...
            temperature=0.0,
            beam_size=5,
            best_of=5,
            patience=1.0,
            no_speech_threshold=0.3,
            logprob_threshold=-1.2,
            compression_ratio_threshold=2.8,
            condition_on_previous_text=True,
            prepend_punctuations="\"'([{-",
            append_punctuations="\"'.,!?:])};",
            hallucination_silence_threshold=0.5,
        )
        
        transcribe_time = time.time() - transcribe_start
        
        # Count words for debugging
        total_words = sum(len(seg.get('words', [])) for seg in result['segments'])
        total_segments = len(result['segments'])
        
        logger.info(f"✅ Transcription complete in {transcribe_time:.1f}s")
        logger.info(f"   Segments: {total_segments}")
        logger.info(f"   Words: {total_words}")
        
        # Calculate processing speed
        if result.get('segments'):
            audio_duration = result['segments'][-1]['end']
            speed_ratio = audio_duration / transcribe_time
            logger.info(f"   Processing speed: {speed_ratio:.2f}x realtime")
        
        if total_words < 50:
            logger.warning(f"⚠️  Low word count ({total_words})! Audio may have issues")
        
        # Log first few words for sanity check
        if total_words > 0:
            first_words = []
            for seg in result['segments'][:3]:
                if 'words' in seg:
                    first_words.extend([w['word'] for w in seg['words'][:5]])
            logger.info(f"   First words: {' '.join(first_words[:10])}")
        
        return result['segments']
        
    except Exception as e:
        logger.error(f"Whisper transcription failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return []
