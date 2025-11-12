# lyrics-fetcher/fetcher.py
import syncedlyrics
import logging

logger = logging.getLogger(__name__)

def clean_title(title):
    """Remove video-specific suffixes from title"""
    suffixes = [
        '(Official Video)', '(Official Music Video)', '(4K Remaster)', 
        '[Official Video]', '[Official Music Video]', '(Lyric Video)',
        '(Audio)', '[Audio]', '(Lyrics)', '[Lyrics]', '(Official)', '[Official]'
    ]
    
    clean = title
    for suffix in suffixes:
        clean = clean.replace(suffix, '').strip()
    
    return clean

def parse_lrc(lrc_content):
    """Parse LRC format into list of {time, text}"""
    import re
    lines = lrc_content.split('\n')
    lyrics = []
    
    for line in lines:
        match = re.match(r'\[(\d{2}):(\d{2})\.(\d{2,3})\](.*)', line)
        if match:
            minutes = int(match.group(1))
            seconds = int(match.group(2))
            milliseconds = int(match.group(3).ljust(3, '0'))
            text = match.group(4).strip()
            
            time_in_seconds = minutes * 60 + seconds + milliseconds / 1000
            
            if text:
                lyrics.append({
                    'time': time_in_seconds,
                    'text': text
                })
    
    return lyrics

def fetch_synced_lyrics(title, artist):
    """
    Fetch lyrics from online sources using syncedlyrics
    Returns: list of {time, text} or None
    """
    try:
        clean_song_title = clean_title(title)
        search_term = f"{artist} {clean_song_title}"
        
        logger.info(f"🔍 Fetching lyrics for: {search_term}")
        
        lrc = syncedlyrics.search(search_term)
        
        if lrc:
            lyrics = parse_lrc(lrc)
            logger.info(f"✅ Found {len(lyrics)} lyrics lines")
            return lyrics
        else:
            logger.warning("No lyrics found")
            return None
            
    except Exception as e:
        logger.error(f"Error fetching lyrics: {e}")
        return None
