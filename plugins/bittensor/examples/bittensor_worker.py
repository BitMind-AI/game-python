from game_sdk.game.worker import Worker
from game_sdk.game.custom_types import (
    Function, 
    Argument, 
    FunctionResult, 
    FunctionResultStatus
)
from typing import Dict, Optional
import os
from dotenv import load_dotenv
import logging
from datetime import datetime

from bittensor_game_sdk.bittensor_plugin import BittensorPlugin
from twitter_plugin_gamesdk.twitter_plugin import TwitterPlugin

from utils.constants import TwitterRateLimitConfig, BittensorRateLimitConfig, CacheConfig, TwitterConfig
from utils.logging import log_performance, ErrorTracker
from utils.cache import Cache
from utils.rate_limiting import RateLimiter
from utils.formatters import format_analysis_response, extract_image_url

class BittensorImageWorker:
    """Worker class for detecting AI-generated images in tweets using Bittensor."""

    def __init__(self):
        """Initialize the worker with required plugins and caches."""
        # Initialize logging
        logging.basicConfig(
            format='[%(asctime)s][%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S',
            level=logging.INFO  # Set to DEBUG to see all logs
        )
        
        self._initialize_environment()
        self._initialize_plugins()
        self.worker = self._create_worker()
        
        # Initialize utilities
        self.twitter_rate_limiter = RateLimiter(
            name="Twitter",
            window_seconds=TwitterRateLimitConfig.WINDOW,
            max_requests=TwitterRateLimitConfig.MAX_REQUESTS,
            buffer=TwitterRateLimitConfig.BUFFER,
            min_sleep=TwitterRateLimitConfig.MIN_SLEEP,
            max_sleep=TwitterRateLimitConfig.MAX_SLEEP
        )
        
        self.bittensor_rate_limiter = RateLimiter(
            name="Bittensor",
            window_seconds=BittensorRateLimitConfig.WINDOW,
            max_requests=BittensorRateLimitConfig.MAX_REQUESTS,
            buffer=BittensorRateLimitConfig.BUFFER,
            min_sleep=BittensorRateLimitConfig.MIN_SLEEP,
            max_sleep=BittensorRateLimitConfig.MAX_SLEEP
        )
        
        self.tweet_cache = Cache[Dict](CacheConfig.EXPIRY)
        self.user_cache = Cache[Dict](CacheConfig.EXPIRY)
        self.analysis_cache = Cache[Dict](CacheConfig.EXPIRY)
        
        self.error_tracker = ErrorTracker()

    def _initialize_environment(self):
        """Initialize and validate environment variables."""
        load_dotenv()
        self.game_api_key = os.environ.get("GAME_API_KEY")

        if not self.game_api_key:
            raise ValueError("GAME_API_KEY not found in environment variables")

        missing_creds = [
            cred for cred in TwitterConfig.REQUIRED_CREDENTIALS
            if not os.environ.get(cred)
        ]
        if missing_creds:
            raise ValueError(f"Missing Twitter credentials: {', '.join(missing_creds)}")

    def _initialize_plugins(self):
        """Initialize Bittensor and Twitter plugins."""
        self.bittensor_plugin = BittensorPlugin()

        try:
            twitter_options = {
                "id": "bittensor_twitter_plugin",
                "name": "Bittensor Twitter Plugin",
                "description": "Twitter Plugin for Bittensor image detection.",
                "credentials": {
                    "bearerToken": os.environ["TWITTER_BEARER_TOKEN"],
                    "apiKey": os.environ["TWITTER_API_KEY"],
                    "apiSecretKey": os.environ["TWITTER_API_SECRET_KEY"],
                    "accessToken": os.environ["TWITTER_ACCESS_TOKEN"],
                    "accessTokenSecret": os.environ["TWITTER_ACCESS_TOKEN_SECRET"],
                    "clientKey": os.environ["TWITTER_CLIENT_KEY"],
                    "clientSecret": os.environ["TWITTER_CLIENT_SECRET"],
                },
            }
            self.twitter_plugin = TwitterPlugin(twitter_options)
        except Exception as e:
            raise RuntimeError(f"Failed to initialize Twitter plugin: {str(e)}")

    def _create_worker(self) -> Worker:
        """Create worker with image detection capability."""
        return Worker(
            api_key=self.game_api_key,
            description="Processing Twitter mentions for BitMind image analysis ONLY when users ask about image authenticity.",
            instruction=(
                "Monitor Twitter mentions and analyze images using BitMind ONLY when "
                "users specifically ask about whether an image is real, AI-generated, "
                "or a deepfake. Ignore mentions that don't explicitly ask about "
                "image authenticity."
            ),  
            get_state_fn=self._get_state,
            action_space=[
                Function(
                    fn_name="detect_image",
                    fn_description="Detect if an image in a tweet is AI-generated",
                    args=[
                        Argument(
                            name="tweet_id",
                            type="string",
                            description="ID of the tweet containing the image to analyze"
                        )
                    ],
                    executable=self.detect_image
                )
            ]
        )
    
    def run(self, tweet_id: str):
        """Run the worker on a single tweet"""
        self.worker.run(f"Analyze tweet: {tweet_id}")

    def _get_state(self, function_result: FunctionResult, current_state: dict) -> dict:
        """Simple state management."""
        return {}
    
    def _post_twitter_reply(self, tweet_id: str, response_text: str) -> None:
        """Post a reply to the tweet."""
        try:
            self.twitter_rate_limiter.wait()
            self.twitter_plugin.twitter_client.create_tweet(
                text=response_text,
                in_reply_to_tweet_id=tweet_id
            )
            logging.info(f"Posted reply to tweet {tweet_id}: {response_text}")
        except Exception as e:
            self.error_tracker.track('twitter_reply_error', "Failed to post reply", e)
            logging.error(f"Failed to post reply: {e}")

    @log_performance(name="detect_image")
    def detect_image(self, tweet_id: str) -> tuple:
        """Detect if an image in a tweet is AI-generated using Bittensor subnet."""
        try:
            logging.info(f"Starting image detection for tweet: {tweet_id}")

            # Format parameters as comma-separated strings
            tweet_fields = ','.join(TwitterConfig.TWEET_FIELDS)
            expansions = ','.join(TwitterConfig.EXPANSIONS)
            user_fields = ','.join(TwitterConfig.USER_FIELDS)
            media_fields = ','.join(TwitterConfig.MEDIA_FIELDS)

            # Get tweet data
            self.twitter_rate_limiter.wait()
            tweet_response = self.twitter_plugin.twitter_client.get_tweet(
                tweet_id,
                tweet_fields=tweet_fields,
                expansions=expansions,
                user_fields=user_fields,
                media_fields=media_fields
            )
            
            logging.debug(f"Tweet response: {tweet_response}")
            
            if not tweet_response or 'data' not in tweet_response:
                return (
                    FunctionResultStatus.FAILED,
                    "Could not retrieve tweet data",
                    {}
                )

            # First check current tweet for image
            image_url, is_root_tweet = extract_image_url(tweet_response)
            root_tweet_data = None
            
            # If no image in current tweet, check root tweet
            if not image_url:
                referenced_tweets = tweet_response['data'].get('referenced_tweets', [])
                root_tweet = next(
                    (ref for ref in referenced_tweets if ref['type'] == 'replied_to'),
                    None
                )
                
                if root_tweet and 'includes' in tweet_response:
                    root_tweet_data = next(
                        (t for t in tweet_response['includes']['tweets'] 
                        if t['id'] == root_tweet['id']),
                        None
                    )
                    if root_tweet_data:
                        root_response = {
                            'data': root_tweet_data,
                            'includes': tweet_response.get('includes', {})
                        }
                        image_url, _ = extract_image_url(root_response)
                        is_root_tweet = bool(image_url)  # Set to True if we found image in root
                        logging.debug(f"Checking root tweet for image. Found: {bool(image_url)}")

            if not image_url:
                return (
                    FunctionResultStatus.FAILED,
                    "No image found to analyze",
                    {}
                )

            # Get usernames from the response
            requester_username = None
            original_poster_username = None
            
            if 'includes' in tweet_response and 'users' in tweet_response['includes']:
                users = tweet_response['includes']['users']
                logging.debug(f"Found users: {[u['username'] for u in users]}")
                
                # Get requester username
                requester = next(
                    (u for u in users if u['id'] == tweet_response['data']['author_id']),
                    None
                )
                if requester:
                    requester_username = requester['username']
                    logging.debug(f"Found requester: {requester_username}")

                # Get original poster username if this is a root tweet with image
                if is_root_tweet and root_tweet_data:
                    logging.debug(f"Root tweet author_id: {root_tweet_data['author_id']}")
                    logging.debug(f"Available user IDs: {[u['id'] for u in users]}")
                    original_poster = next(
                        (u for u in users if u['id'] == root_tweet_data['author_id']),
                        None
                    )
                    if original_poster:
                        original_poster_username = original_poster['username']
                        logging.debug(f"Found original poster: {original_poster_username}")
                    else:
                        logging.warning("Could not find original poster in users list")

            # Check cache before making Bittensor call
            cached_analysis = self.analysis_cache.get(image_url)
            if cached_analysis:
                response = format_analysis_response(
                    is_ai=cached_analysis.get('isAI', False),
                    confidence=round(cached_analysis.get('confidence', 0) * 100, 2),
                    requester_username=requester_username,
                    original_poster_username=original_poster_username,
                    is_root_tweet=is_root_tweet
                )
                self._post_twitter_reply(tweet_id, response)
                return (FunctionResultStatus.DONE, response, cached_analysis)

            # Analyze image if not cached
            try:
                self.bittensor_rate_limiter.wait()
                result = self.bittensor_plugin.call_subnet(
                    34,
                    {"image": image_url}
                )
                
                if not result:
                    self.error_tracker.track('analysis_error', "Empty response from Bittensor API")
                    return (
                        FunctionResultStatus.FAILED,
                        "No analysis result available",
                        {}
                    )
                
                if not isinstance(result, dict) or 'isAI' not in result or 'confidence' not in result:
                    self.error_tracker.track('analysis_error', "Invalid response format from Bittensor API")
                    return (
                        FunctionResultStatus.FAILED,
                        "Invalid analysis result format",
                        {}
                    )
                
                self.analysis_cache.set(image_url, result)
                
                response = format_analysis_response(
                    is_ai=result.get('isAI', False),
                    confidence=round(result.get('confidence', 0) * 100, 2),
                    requester_username=requester_username,
                    original_poster_username=original_poster_username,
                    is_root_tweet=is_root_tweet
                )
                
                self._post_twitter_reply(tweet_id, response)
                return (FunctionResultStatus.DONE, response, result)

            except Exception as e:
                self.error_tracker.track('analysis_error', "Error calling Bittensor API", e)
                return (FunctionResultStatus.FAILED, f"Analysis failed: {str(e)}", {})

        except Exception as e:
            self.error_tracker.track('general_error', "Error in detect_image", e)
            return (FunctionResultStatus.FAILED, f"Operation failed: {str(e)}", {})
        
def main():
    worker = BittensorImageWorker()
    test_tweet_id = "1891988999834828838"
    worker.run(test_tweet_id)

if __name__ == "__main__":
    main()