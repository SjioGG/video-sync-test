# lyrics-fetcher/aligner.py
import logging
from rapidfuzz import fuzz
import re
import numpy as np

logger = logging.getLogger(__name__)

def normalize_text(text):
    """Normalize text for comparison"""
    text = re.sub(r'[^\w\s]', '', text.lower())
    text = ' '.join(text.split())
    return text

def compute_similarity_matrix(fetched_words, whisper_words):
    """Compute similarity between all fetched and whisper words"""
    n_fetched = len(fetched_words)
    n_whisper = len(whisper_words)
    
    similarity = np.zeros((n_fetched, n_whisper))
    
    for i, fw in enumerate(fetched_words):
        for j, ww in enumerate(whisper_words):
            score = fuzz.ratio(
                fw['word_normalized'],
                ww['word_normalized']
            ) / 100.0
            similarity[i, j] = score
    
    return similarity

def dtw_align(fetched_words, whisper_words):
    """Dynamic Time Warping alignment"""
    n_fetched = len(fetched_words)
    n_whisper = len(whisper_words)
    
    # Compute similarity matrix
    similarity = compute_similarity_matrix(fetched_words, whisper_words)
    
    # DTW cost matrix
    cost = np.zeros((n_fetched + 1, n_whisper + 1))
    cost[0, :] = np.inf
    cost[:, 0] = np.inf
    cost[0, 0] = 0
    
    # Fill cost matrix
    for i in range(1, n_fetched + 1):
        for j in range(1, n_whisper + 1):
            match_cost = 1 - similarity[i-1, j-1]  # Convert similarity to cost
            cost[i, j] = match_cost + min(
                cost[i-1, j-1],  # Match
                cost[i-1, j] + 0.5,    # Delete fetched word (gap in whisper)
                cost[i, j-1] + 0.5     # Insert whisper word (extra word)
            )
    
    # Backtrack to find alignment path
    i, j = n_fetched, n_whisper
    alignment = []
    
    while i > 0 and j > 0:
        current_cost = cost[i, j]
        
        # Check which path was taken
        if i > 0 and j > 0 and current_cost == (1 - similarity[i-1, j-1]) + cost[i-1, j-1]:
            # Match
            alignment.append((i-1, j-1))
            i -= 1
            j -= 1
        elif i > 0 and current_cost == cost[i-1, j] + 0.5:
            # Delete (skip fetched word)
            i -= 1
        else:
            # Insert (skip whisper word)
            j -= 1
    
    alignment.reverse()
    return alignment

def align_words_with_whisper(fetched_lyrics, whisper_transcription):
    """
    IMPROVED: DTW-based alignment for robust word matching
    """
    try:
        if not whisper_transcription:
            logger.warning("No Whisper transcription available")
            return []
        
        # Extract Whisper word timings
        whisper_words = []
        for segment in whisper_transcription:
            if 'words' in segment and segment['words']:
                for word_data in segment['words']:
                    whisper_words.append({
                        'word_normalized': normalize_text(word_data['word']),
                        'word_raw': word_data['word'].strip(),
                        'start': word_data['start'],
                        'end': word_data['end']
                    })
        
        if not whisper_words:
            logger.warning("No word-level timestamps from Whisper")
            return []
        
        logger.info(f"🎤 Whisper: {len(whisper_words)} words")
        logger.info(f"   Duration: {whisper_words[0]['start']:.2f}s → {whisper_words[-1]['end']:.2f}s")
        
        if not fetched_lyrics:
            logger.warning("No fetched lyrics, using Whisper directly")
            return [{
                'word': w['word_raw'],
                'start': w['start'],
                'end': w['end'],
                'confidence': 0.7
            } for w in whisper_words]
        
        # Extract words from fetched lyrics
        fetched_words = []
        for line in fetched_lyrics:
            words_in_line = line['text'].split()
            for word in words_in_line:
                fetched_words.append({
                    'word_original': word,
                    'word_normalized': normalize_text(word)
                })
        
        logger.info(f"📄 Fetched: {len(fetched_words)} words")
        
        # DTW alignment
        logger.info("🔄 Running DTW alignment...")
        alignment = dtw_align(fetched_words, whisper_words)
        
        # Build aligned words
        aligned_words = []
        whisper_idx = 0
        
        for i, fetched_word in enumerate(fetched_words):
            # Find if this fetched word is in alignment
            matched_whisper_idx = None
            for f_idx, w_idx in alignment:
                if f_idx == i:
                    matched_whisper_idx = w_idx
                    break
            
            if matched_whisper_idx is not None:
                # Matched via DTW
                matched = whisper_words[matched_whisper_idx]
                similarity = fuzz.ratio(
                    fetched_word['word_normalized'],
                    matched['word_normalized']
                ) / 100.0
                
                aligned_words.append({
                    'word': fetched_word['word_original'],
                    'start': matched['start'],
                    'end': matched['end'],
                    'confidence': similarity,
                    'source': 'dtw_matched'
                })
                whisper_idx = matched_whisper_idx + 1
            else:
                # Not matched - interpolate timing
                if aligned_words:
                    prev = aligned_words[-1]
                    duration = 0.25  # Default word duration
                    
                    # Try to find next matched word for better interpolation
                    next_match = None
                    for j in range(i + 1, len(fetched_words)):
                        for f_idx, w_idx in alignment:
                            if f_idx == j:
                                next_match = whisper_words[w_idx]
                                break
                        if next_match:
                            break
                    
                    if next_match:
                        gap = next_match['start'] - prev['end']
                        words_between = j - i
                        duration = gap / words_between if words_between > 0 else 0.25
                    
                    aligned_words.append({
                        'word': fetched_word['word_original'],
                        'start': prev['end'],
                        'end': prev['end'] + duration,
                        'confidence': 0.3,
                        'source': 'interpolated'
                    })
                else:
                    # First word, use first whisper timestamp
                    aligned_words.append({
                        'word': fetched_word['word_original'],
                        'start': whisper_words[0]['start'],
                        'end': whisper_words[0]['start'] + 0.25,
                        'confidence': 0.3,
                        'source': 'extrapolated'
                    })
        
        logger.info(f"✅ Aligned {len(aligned_words)} words")
        
        if aligned_words:
            logger.info(f"   Range: {aligned_words[0]['start']:.2f}s → {aligned_words[-1]['end']:.2f}s")
        
        # Quality breakdown
        sources = {}
        for w in aligned_words:
            sources[w['source']] = sources.get(w['source'], 0) + 1
        
        logger.info(f"   Quality breakdown:")
        for source, count in sorted(sources.items()):
            pct = (count / len(aligned_words)) * 100
            logger.info(f"     {source}: {count} ({pct:.1f}%)")
        
        avg_conf = sum(w['confidence'] for w in aligned_words) / len(aligned_words)
        logger.info(f"   Avg confidence: {avg_conf:.2f}")
        
        return aligned_words
        
    except Exception as e:
        logger.error(f"Alignment error: {e}", exc_info=True)
        return []

def export_word_level_lrc(aligned_words, output_path):
    """Export LRC with punctuation-aware line breaks"""
    import re
    
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            if not aligned_words:
                return False
            
            current_line = []
            
            for i, word in enumerate(aligned_words):
                current_line.append(word)
                
                is_last = (i == len(aligned_words) - 1)
                
                # Check if word ends with sentence-ending punctuation
                ends_with_punctuation = bool(re.search(r'[.!?]$', word['word']))
                
                # Calculate metrics
                gap_to_next = 0
                if not is_last:
                    gap_to_next = aligned_words[i + 1]['start'] - word['end']
                
                line_duration = word['end'] - current_line[0]['start']
                line_chars = len(' '.join([w['word'] for w in current_line]))
                
                # Break on:
                # 1. Punctuation (NOT comma)
                # 2. Large gap (1.5s+)
                # 3. Max chars (100+)
                # 4. Max duration (10s+)
                should_break = (
                    is_last or
                    (ends_with_punctuation and word['word'][-1] != ',') or
                    gap_to_next > 1.5 or
                    line_chars > 100 or
                    line_duration > 10.0
                )
                
                if should_break and current_line:
                    start = current_line[0]['start']
                    minutes = int(start // 60)
                    seconds = int(start % 60)
                    millis = int((start % 1) * 1000)
                    
                    text = ' '.join([w['word'] for w in current_line])
                    # Remove trailing punctuation from line if present
                    text = text.rstrip('.!?')
                    f.write(f"[{minutes:02d}:{seconds:02d}.{millis:03d}]{text}\n")
                    
                    current_line = []
        
        logger.info(f"💾 Exported LRC: {output_path}")
        return True
    except Exception as e:
        logger.error(f"Export error: {e}", exc_info=True)
        return False


def export_word_timestamps_json(aligned_words, output_path):
    """Export word-level JSON for video generator"""
    import json
    try:
        json_path = output_path.replace('.lrc', '_words.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(aligned_words, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Exported JSON: {json_path}")
        return json_path
    except Exception as e:
        logger.error(f"JSON export error: {e}", exc_info=True)
        return None
