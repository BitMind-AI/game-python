import logging
import time
from typing import Optional

class RateLimiter:
    """Manages API rate limiting with exponential backoff."""

    def __init__(
        self,
        name: str,
        window_seconds: int,
        max_requests: int,
        buffer: int = 1,
        min_sleep: int = 60,
        max_sleep: int = 900
    ):
        self.name = name
        self.window_seconds = window_seconds
        self.max_requests = max_requests
        self.buffer = buffer
        self.min_sleep = min_sleep
        self.max_sleep = max_sleep
        self._last_request = 0
        self._requests_count = 0

    def wait(self) -> None:
        """Wait if rate limit is approaching."""
        current_time = time.time()
        
        # Reset counter if window has passed
        if current_time - self._last_request > self.window_seconds:
            self._requests_count = 0
            self._last_request = current_time
            logging.info(f"{self.name} rate limit window reset")

        # Check if we need to wait
        if self._requests_count >= self.max_requests - self.buffer:
            wait_time = self.window_seconds - (current_time - self._last_request)
            if wait_time > 0:
                logging.info(
                    f"{self.name} rate limit wait: {wait_time:.1f}s "
                    f"({self._requests_count}/{self.max_requests} requests)"
                )
                time.sleep(wait_time)
                self._requests_count = 0
                self._last_request = time.time()

        self._requests_count += 1
        logging.info(f"{self.name} requests in window: {self._requests_count}")
        
    def handle_rate_limit(self, attempt: int, max_retries: int, 
                         error: Optional[Exception] = None) -> bool:
        """Handle rate limit errors with exponential backoff."""
        if attempt >= max_retries - 1:
            return False

        if error and not self._is_rate_limit_error(error):
            return False

        base_wait = 180 if error else self.min_sleep
        wait_time = min(base_wait * (2 ** attempt), self.max_sleep)
        
        logging.info(
            f"Rate limit backoff: Attempt {attempt + 1}/{max_retries}, "
            f"waiting {wait_time}s"
        )
        time.sleep(wait_time)
        return True

    @staticmethod
    def _is_rate_limit_error(error: Exception) -> bool:
        """Check if error is rate limit related."""
        error_str = str(error).lower()
        return "429" in error_str or "rate limit" in error_str