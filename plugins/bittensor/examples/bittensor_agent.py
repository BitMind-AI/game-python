from game_sdk.game.agent import Agent, WorkerConfig
from game_sdk.game.worker import Worker
from game_sdk.game.custom_types import Function, Argument, FunctionResult, FunctionResultStatus
from typing import Optional, Dict, List
import os
from dotenv import load_dotenv
import threading
import time
from datetime import datetime, timezone, timedelta
from bittensor_worker import BittensorImageWorker

# Constants for Twitter API rate limits
CHECK_INTERVAL_MINUTES = 15  # Twitter's rate limit window
MAX_MENTIONS_PER_CHECK = 7   # Limit to avoid rate limits
LOOKBACK_MINUTES = 45        # How far back to look for mentions

# Load environment variables
load_dotenv()

# Initialize worker
bittensor_worker = BittensorImageWorker()

def check_mentions(**kwargs) -> tuple:
    """Function to process Twitter mentions and analyze images."""
    try:
        # Calculate the cutoff time with RFC3339 formatting
        cutoff_time = datetime.now(timezone.utc) - timedelta(minutes=LOOKBACK_MINUTES)
        formatted_time = cutoff_time.strftime('%Y-%m-%dT%H:%M:%SZ')
        print(f"[INFO] Processing mentions after: {formatted_time}")
        
        try:
            # Cache bot ID to reduce API calls
            if not hasattr(check_mentions, '_bot_id'):
                me = bittensor_worker.twitter_plugin.twitter_client.get_me()
                if not me or not isinstance(me, dict) or 'data' not in me:
                    print("[ERROR] Could not retrieve bot's user ID")
                    return FunctionResultStatus.FAILED, "Failed to get bot's user ID", {}
                check_mentions._bot_id = me['data']['id']
            
            # Get mentions
            mentions = bittensor_worker.twitter_plugin.twitter_client.get_users_mentions(
                id=check_mentions._bot_id,
                max_results=MAX_MENTIONS_PER_CHECK,
                tweet_fields=['id', 'created_at', 'text'],
                start_time=formatted_time 
            )
        except Exception as e:
            if "429" in str(e):
                wait_time = 900  # 15 minutes in seconds
                print(f"[WARN] Rate limit hit, waiting {wait_time} seconds...")
                time.sleep(wait_time)
                return FunctionResultStatus.FAILED, "Rate limit hit, waiting for reset", {}
            raise e

        if not mentions or not isinstance(mentions, dict):
            return FunctionResultStatus.DONE, "No mentions retrieved", {}
        
        mentions_data = mentions.get('data', [])
        
        if not mentions_data:
            return FunctionResultStatus.DONE, "No mentions data available", {}
        
        processed_count = 0
        analyzed_count = 0
        skipped_count = 0

        for mention in mentions_data:
            if not isinstance(mention, dict) or 'id' not in mention:
                print(f"Invalid mention data: {mention}")
                continue
            
            tweet_time = datetime.fromisoformat(mention['created_at'].replace('Z', '+00:00'))

            # Skip tweets older than cutoff
            if tweet_time < cutoff_time:
                print(f"[INFO] Skipping tweet {mention['id']} from {tweet_time.isoformat()} - too old")
                skipped_count += 1
                continue
            
            tweet_id = str(mention['id'])
            print(f"\n[INFO] Processing mention tweet ID: {tweet_id} from {tweet_time.isoformat()}")
            
            time.sleep(5)  # Rate limiting protection

            # Use the bittensor worker to analyze the tweet
            try:
                status, message, result = bittensor_worker.detect_image(tweet_id)
                if status == FunctionResultStatus.DONE:
                    analyzed_count += 1
                print(f"[INFO] Analysis result: {message}")
            except Exception as e:
                if "429" in str(e):
                    print("[WARN] Rate limit hit during analysis, waiting 60 seconds...")
                    time.sleep(60)
                    try:
                        # One retry after rate limit wait
                        status, message, result = bittensor_worker.detect_image(tweet_id)
                        if status == FunctionResultStatus.DONE:
                            analyzed_count += 1
                        print(f"[INFO] Retry analysis result: {message}")
                    except Exception as retry_e:
                        print(f"[ERROR] Failed to analyze tweet {tweet_id} on retry: {retry_e}")
                        if "429" in str(retry_e):
                            return FunctionResultStatus.FAILED, "Rate limit persists after retry", {}
                else:
                    print(f"[ERROR] Failed to analyze tweet {tweet_id}: {e}")
            
            processed_count += 1
        
        result_message = (
            f"Processed {processed_count} mentions, "
            f"analyzed {analyzed_count} images, "
            f"skipped {skipped_count} old tweets"
        )
        print(f"\n[SUMMARY] {result_message}")
        return FunctionResultStatus.DONE, result_message, {}

    except Exception as e:
        error_msg = f"Error encountered while processing mentions: {str(e)}"
        print(f"[ERROR] {error_msg}")
        if "429" in str(e):
            time.sleep(60)
        return FunctionResultStatus.FAILED, error_msg, {}

# Action space with image analysis capability
action_space = [
    Function(
        fn_name="check_mentions",
        fn_description="Check Twitter mentions for images to analyze",
        args=[],
        executable=check_mentions
    )
]

# Create worker with updated description
worker = Worker(
    api_key=bittensor_worker.game_api_key,
    description="Processing Twitter mentions for BitMind image analysis when users ask about image authenticity.",
    instruction=(
        "Monitor Twitter mentions and analyze images using BitMind only when "
        "users specifically ask about whether an image is real, AI-generated, "
        "or a deepfake."
    ),
    get_state_fn=bittensor_worker._get_state,
    action_space=action_space
)

def check_mentions_loop():
    """Periodically check for new mentions to process."""
    while True:
        try:
            print("\n[INFO] Starting new mention check cycle...")
            worker.run("Check Twitter mentions for image analysis requests")
            
            next_check = datetime.now() + timedelta(minutes=CHECK_INTERVAL_MINUTES)
            print(f"[INFO] Next check scheduled for: {next_check.strftime('%Y-%m-%d %H:%M:%S')}")
            
            # Sleep until next check interval
            time.sleep(CHECK_INTERVAL_MINUTES * 60)
            
        except Exception as e:
            print(f"[ERROR] Error in check_mentions loop: {e}")
            # On error, wait at least 5 minutes before retry
            time.sleep(300)

# Create mention checker thread
mention_checker = threading.Thread(target=check_mentions_loop, daemon=True)

if __name__ == "__main__":
    # Start thread
    print("Starting detection agent...")
    mention_checker.start()
    
    try:
        # Keep main thread alive
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Shutting down...")