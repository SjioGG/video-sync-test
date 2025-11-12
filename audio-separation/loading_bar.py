# audio-separation/loading_bar.py
import logging
import threading
import time

logger = logging.getLogger(__name__)

class LoadingBar:
    """Activity indicator for audio separation"""
    
    def __init__(self, description="Processing"):
        self.description = description
        self.running = False
        self.thread = None
        self._spinner_chars = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self._spinner_idx = 0
        
    def _spinner_loop(self):
        """Background thread to show spinner animation"""
        start_time = time.time()
        while self.running:
            elapsed = int(time.time() - start_time)
            minutes = elapsed // 60
            seconds = elapsed % 60
            spinner = self._spinner_chars[self._spinner_idx % len(self._spinner_chars)]
            
            logger.info(f"{spinner} {self.description}... [{minutes:02d}:{seconds:02d}]")
            
            self._spinner_idx += 1
            time.sleep(2)  # Update every 2 seconds
    
    def start(self):
        """Start showing activity"""
        self.running = True
        self.thread = threading.Thread(target=self._spinner_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop the activity indicator"""
        self.running = False
        if self.thread:
            self.thread.join(timeout=3)
        
    def complete(self):
        """Mark as complete"""
        self.stop()
        logger.info(f"✅ {self.description} complete!")

