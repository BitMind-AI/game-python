from dataclasses import dataclass
from typing import Tuple

@dataclass(frozen=True)
class TwitterRateLimitConfig:
    """Twitter API rate limiting configuration."""
    WINDOW: int = 900  # 15 minutes
    MIN_SLEEP: int = 60
    MAX_SLEEP: int = 900
    BUFFER: int = 1
    MAX_REQUESTS: int = 15
    MAX_RETRIES: int = 3

@dataclass(frozen=True)
class BittensorRateLimitConfig:
    """Bittensor API rate limiting configuration."""
    WINDOW: int = 60  # 1 minute
    MIN_SLEEP: int = 1
    MAX_SLEEP: int = 30
    BUFFER: int = 0
    MAX_REQUESTS: int = 100
    MAX_RETRIES: int = 3
        
@dataclass(frozen=True)
class CacheConfig:
    """Cache configuration."""
    EXPIRY: int = 3600  # 1 hour cache expiry
    CLEANUP_INTERVAL: int = 300  # 5 minutes between cleanup runs

@dataclass(frozen=True)
class TwitterConfig:
    """Twitter API configuration."""
    TWEET_FIELDS: Tuple[str, ...] = (
        'referenced_tweets',
        'author_id',
        'attachments'
    )
    EXPANSIONS: Tuple[str, ...] = (
        'referenced_tweets.id',
        'attachments.media_keys',
        'author_id',
        'referenced_tweets.id.author_id',
        'referenced_tweets.id.attachments.media_keys'
    )
    USER_FIELDS: Tuple[str, ...] = (
        'username',
    )
    MEDIA_FIELDS: Tuple[str, ...] = (
        'type',
        'url',
        'preview_image_url',
        'media_key'
    )
    REQUIRED_CREDENTIALS: Tuple[str, ...] = (
        "TWITTER_BEARER_TOKEN",
        "TWITTER_API_KEY",
        "TWITTER_API_SECRET_KEY",
        "TWITTER_ACCESS_TOKEN",
        "TWITTER_ACCESS_TOKEN_SECRET",
        "TWITTER_CLIENT_KEY",
        "TWITTER_CLIENT_SECRET"
    )