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
import time
from bittensor_game_sdk.bittensor_plugin import BittensorPlugin
from twitter_plugin_gamesdk.twitter_plugin import TwitterPlugin

class BittensorImageWorker:
    def __init__(self):
        self._initialize_environment()
        self._initialize_plugins()
        self.worker = self._create_worker()
        
    def _initialize_environment(self):
        """Initialize and validate environment variables."""
        load_dotenv()
        self.game_api_key = os.environ.get("GAME_API_KEY")

        if not self.game_api_key:
            raise ValueError("GAME_API_KEY not found in environment variables")

        required_twitter_creds = [
            "TWITTER_BEARER_TOKEN",
            "TWITTER_API_KEY",
            "TWITTER_API_SECRET_KEY",
            "TWITTER_ACCESS_TOKEN",
            "TWITTER_ACCESS_TOKEN_SECRET",
            "TWITTER_CLIENT_KEY",
            "TWITTER_CLIENT_SECRET"
        ]

        missing_creds = [
            cred for cred in required_twitter_creds
            if not os.environ.get(cred)
        ]
        if missing_creds:
            raise ValueError(
                f"Missing Twitter credentials: {', '.join(missing_creds)}"
            )
    
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
    
    def _get_state(self, function_result: FunctionResult, current_state: dict) -> dict:
        """Simple state management"""
        return {}
    
    def _get_tweet_data(self, tweet_id: str) -> Optional[Dict]:
        """Get tweet data with specified fields."""
        max_retries = 3
        base_wait_time = 60  # seconds
        
        for attempt in range(max_retries):
            try:
                return self.twitter_plugin.twitter_client.get_tweet(
                    tweet_id,
                    tweet_fields=['conversation_id', 'referenced_tweets', 'text', 'author_id'],
                    expansions=['referenced_tweets.id', 'attachments.media_keys'],
                    media_fields=['type', 'url', 'preview_image_url', 'media_key']
                )
            except Exception as e:
                if "429" in str(e):  # Rate limit error
                    wait_time = base_wait_time * (attempt + 1)
                    print(f"[WARN] Rate limit hit, waiting {wait_time} seconds (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        raise RuntimeError(f"Rate limit persisted after {max_retries} retries")
                    continue
                print(f"Error getting tweet data: {e}")
                return None
    
    def _extract_image_url(self, tweet_data) -> Optional[str]:
        """Extract image URL from tweet data, handling both uploaded images and URLs."""
        try:
            if not tweet_data or 'includes' not in tweet_data:
                return None

            # Check if tweet has media attachments
            media = tweet_data.get('includes', {}).get('media', [])
            for item in media:
                # Handle different types of media
                media_type = item.get('type')
                
                if media_type == 'photo':
                    # Direct photo uploads use the url field
                    return item.get('url')
                elif media_type in ('video', 'animated_gif'):
                    # Videos and GIFs use preview_image_url
                    return item.get('preview_image_url')
                
            # If no media attachments found, try to find URL in tweet text
            if 'data' in tweet_data and 'text' in tweet_data['data']:
                words = tweet_data['data']['text'].split()
                for word in words:
                    if word.startswith(('http://pbs.twimg.com', 'https://pbs.twimg.com')):
                        return word

            return None
        except Exception as e:
            print(f"Error extracting image URL: {e}")
            return None
    
    def _format_tweet_data(self, tweet_data) -> Dict:
        """Format tweet data into consistent structure."""
        # Handle tweet_data as a dictionary instead of an object
        return {
            'id': str(tweet_data['id']),
            'text': tweet_data['text'],
            'author_id': tweet_data['author_id']
        }

    def _get_original_tweet(self, tweet_id: str) -> Optional[Dict]:
        """Get the original (root) tweet of a thread."""
        max_retries = 3
        base_wait_time = 60  # seconds
        
        for attempt in range(max_retries):
            try:
                current_tweet = self._get_tweet_data(tweet_id)
                if not current_tweet or 'data' not in current_tweet:
                    raise ValueError(f"Tweet with ID {tweet_id} not found")

                # Access dictionary values instead of attributes
                referenced_tweets = current_tweet['data'].get('referenced_tweets')
                if not referenced_tweets:
                    return self._format_tweet_data(current_tweet['data'])

                while referenced_tweets:
                    parent_ref = next(
                        (ref for ref in referenced_tweets if ref['type'] == 'replied_to'),
                        None
                    )
                    if not parent_ref:
                        break

                    time.sleep(2)  # Rate limit protection
                    
                    current_tweet = self._get_tweet_data(str(parent_ref['id']))
                    if not current_tweet or 'data' not in current_tweet:
                        break
                    
                    referenced_tweets = current_tweet['data'].get('referenced_tweets')

                return self._format_tweet_data(current_tweet['data'])
        
            except Exception as e:
                if "429" in str(e):  # Rate limit error
                    wait_time = base_wait_time * (attempt + 1)
                    print(f"[WARN] Rate limit hit, waiting {wait_time} seconds (attempt {attempt + 1}/{max_retries})...")
                    time.sleep(wait_time)
                    if attempt == max_retries - 1:
                        raise RuntimeError(f"Rate limit persisted after {max_retries} retries")
                    continue
                raise
    
    def detect_image(self, tweet_id: str) -> tuple:
        """Detect if an image in a tweet is AI-generated using Bittensor subnet"""
        try:
            # Get the original tweet in case we need to check it for images
            original_tweet = self._get_original_tweet(tweet_id)
            if not original_tweet:
                return FunctionResultStatus.FAILED, "Could not retrieve original tweet", {}

            # Get author username for mentions
            try:
                author_data = self.twitter_plugin.twitter_client.get_user(id=original_tweet['author_id'])
                author_username = author_data['data']['username']
            except Exception as e:
                print(f"Error getting author username: {e}")
                author_username = original_tweet['author_id']

            # First try to get image from reply tweet
            reply_tweet_data = self._get_tweet_data(tweet_id)
            image_url = self._extract_image_url(reply_tweet_data)
            image_source = "reply"
            
            # If no image in reply, check original tweet
            if not image_url and tweet_id != original_tweet['id']:
                original_tweet_data = self._get_tweet_data(original_tweet['id'])
                image_url = self._extract_image_url(original_tweet_data)
                if image_url:
                    image_source = "original"
                    print(f"Using image from original tweet by @{author_username}")

            if not image_url:
                return FunctionResultStatus.FAILED, "No image found in tweet thread", {}

            print(f"Processing image from {image_source} tweet: {tweet_id}")
            print(f"Image URL: {image_url}")
            
            # Add retry logic for Bittensor API
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = self.bittensor_plugin.call_subnet(34, {"image": image_url})
                    
                    if result.get('statusCode') in (400, 500):
                        if attempt < max_retries - 1:
                            wait_time = (attempt + 1) * 5  # Exponential backoff
                            print(f"Attempt {attempt + 1} failed, waiting {wait_time} seconds...")
                            time.sleep(wait_time)
                            continue
                        return FunctionResultStatus.FAILED, f"API Error: {result.get('message')}", result
                    
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    if attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        print(f"Attempt {attempt + 1} failed with error: {e}, waiting {wait_time} seconds...")
                        time.sleep(wait_time)
                        continue
                    return FunctionResultStatus.FAILED, f"Error calling Bittensor API: {str(e)}", {}
                
            try:
                # Process Bittensor result
                is_ai = result.get('isAI', False)
                raw_confidence = result.get('confidence', 0)
                
                # Convert confidence to a more readable percentage (0-100)
                confidence = round(raw_confidence * 100, 2)
                confidence = max(confidence, 0.01)  # Minimum display value of 0.01%
                
                # Generate response text
                if tweet_id != original_tweet['id']:
                    response_text = f"@{author_username} SN34 Media Analysis: "
                else:
                    response_text = "SN34 Media Analysis: "

                response_text += f"{'AI-Generated' if is_ai else 'Not AI-Generated'} ({confidence}%)"
                response_text += "\nhttps://github.com/BitMind-AI/bitmind-subnet"
                
                # Add debug info to console but not to tweet
                print(f"Debug - Raw confidence: {raw_confidence}")
                print(f"Debug - Scaled confidence: {confidence}%")
                print(f"Debug - Is AI: {is_ai}")
                print(f"Debug - Response text: {response_text}")
                
                # Post the response
                reply_tweet_fn = self.twitter_plugin.get_function('reply_tweet')
                reply_tweet_fn(tweet_id, response_text)
                
                return FunctionResultStatus.DONE, "Image detection successful", result
                
            except Exception as e:
                print(f"Error detecting image: {e}")
                return FunctionResultStatus.FAILED, f"Error: {str(e)}", {}
                
        except Exception as e:
            print(f"Error detecting image: {e}")
            return FunctionResultStatus.FAILED, f"Error: {str(e)}", {}

    def _create_worker(self) -> Worker:
        """Create worker with image detection capability"""
        return Worker(
            api_key=self.game_api_key,
            description="Worker for detecting AI-generated images using Bittensor",
            instruction="Analyze images to determine if they are AI-generated",
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

def main():
    worker = BittensorImageWorker()
    # Example tweet ID with an image
    test_tweet_id = "1890177288194699356"  # Replace with a real tweet ID
    worker.run(test_tweet_id)

if __name__ == "__main__":
    main()
