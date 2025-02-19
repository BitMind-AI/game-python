import logging
from functools import wraps
import time
from typing import Dict, Optional, Callable, Any, TypeVar, cast

F = TypeVar('F', bound=Callable[..., Any])

def configure_logging(level: int = logging.INFO) -> None:
    """Configure logging with standard format."""
    logging.basicConfig(
        format='[%(asctime)s][%(levelname)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        level=level
    )

def log_performance(name: Optional[str] = None) -> Callable[[F], F]:
    """Decorator to log function performance."""
    def decorator(func: F) -> F:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            start_time = time.time()
            result = func(*args, **kwargs)
            duration = time.time() - start_time
            operation = name or func.__name__
            logging.info(f"{operation} took {duration:.2f} seconds")
            return result
        return cast(F, wrapper)
    return decorator

class PerformanceTracker:
    def __init__(self):
        self.metrics: Dict[str, List[float]] = defaultdict(list)
    
    def track(self, operation: str, duration: float):
        self.metrics[operation].append(duration)
    
    def get_stats(self) -> Dict[str, Dict[str, float]]:
        return {
            op: {
                'avg': sum(times)/len(times),
                'min': min(times),
                'max': max(times),
                'count': len(times)
            }
            for op, times in self.metrics.items()
        }
        
class ErrorTracker:
    """Tracks error occurrences with automatic reset."""

    def __init__(self, reset_interval: int = 3600, alert_threshold: int = 10):
        self._error_counts: Dict[str, int] = {}
        self._last_reset = time.time()
        self._reset_interval = reset_interval
        self._alert_threshold = alert_threshold

    def track(self, error_type: str, context: Optional[str] = None, 
              error: Optional[Exception] = None) -> None:
        """Track an error occurrence with optional context."""
        self._check_reset()
        self._increment_count(error_type)
        self._log_error(error_type, context, error)

    def _check_reset(self) -> None:
        """Reset error counts if interval has passed."""
        current_time = time.time()
        if current_time - self._last_reset > self._reset_interval:
            self._error_counts.clear()
            self._last_reset = current_time

    def _increment_count(self, error_type: str) -> None:
        """Increment error count and check threshold."""
        self._error_counts[error_type] = self._error_counts.get(error_type, 0) + 1
        if self._error_counts[error_type] > self._alert_threshold:
            logging.warning(
                f"High {error_type} error rate: "
                f"{self._error_counts[error_type]} in the last hour"
            )

    def _log_error(self, error_type: str, context: Optional[str], 
                   error: Optional[Exception]) -> None:
        """Log error details."""
        if context or error:
            error_msg = f"{error_type.upper()}: {context or ''}"
            if error:
                error_msg += f" - {str(error)}"
            logging.error(error_msg)