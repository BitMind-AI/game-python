from dataclasses import dataclass
from typing import Dict, Generic, TypeVar, Optional
import time
import logging

T = TypeVar('T')

@dataclass
class CacheEntry(Generic[T]):
    data: T
    timestamp: float

class Cache(Generic[T]):
    """Thread-safe cache with automatic expiration and cleanup."""
    
    def __init__(self, expiry_seconds: int, cleanup_interval: int = 300):
        """Initialize cache with expiry and cleanup settings.
        
        Args:
            expiry_seconds: Time in seconds before entries expire
            cleanup_interval: Time in seconds between cleanup runs
        """
        self._cache: Dict[str, CacheEntry[T]] = {}
        self._expiry_seconds = expiry_seconds
        self._cleanup_interval = cleanup_interval
        self._last_cleanup = time.time()

    def get(self, key: str) -> Optional[T]:
        """Get value from cache if it exists and isn't expired."""
        if not key:
            return None

        if self._cache and self._should_cleanup():
            self._cleanup()

        entry = self._cache.get(key)
        if not entry:
            return None

        if self._is_expired(entry.timestamp):
            del self._cache[key]
            return None

        return entry.data
    
    def get_many(self, keys: list[str]) -> Dict[str, Optional[T]]:
        """Get multiple values from cache at once."""
        if self._cache and self._should_cleanup():
            self._cleanup()
        
        result = {}
        for key in keys:
            entry = self._cache.get(key)
            if not entry or self._is_expired(entry.timestamp):
                result[key] = None
                if entry:
                    del self._cache[key]
            else:
                result[key] = entry.data
        return result

    def set(self, key: str, value: T) -> None:
        """Set cache value with current timestamp."""
        if not key:
            return
        self._cache[key] = CacheEntry(value, time.time())

    def _should_cleanup(self) -> bool:
        return time.time() - self._last_cleanup > self._cleanup_interval

    def _is_expired(self, timestamp: float) -> bool:
        return time.time() - timestamp > self._expiry_seconds

    def _cleanup(self) -> None:
        """Remove expired entries and update cleanup timestamp."""
        try:
            current_time = time.time()
            initial_size = len(self._cache)
            
            self._cache = {
                k: v for k, v in self._cache.items()
                if not self._is_expired(v.timestamp)
            }
            
            cleaned = initial_size - len(self._cache)
            if cleaned > 0:
                logging.info(f"Cleaned {cleaned} expired cache entries")
            
            self._last_cleanup = current_time
        except Exception as e:
            logging.error(f"Cache cleanup failed: {e}")