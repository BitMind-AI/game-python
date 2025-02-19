from typing import Dict, Optional
import logging


def format_analysis_response(
    is_ai: bool,
    confidence: float,
    requester_username: Optional[str],
    original_poster_username: Optional[str],
    is_root_tweet: bool
) -> str:
    """Format the analysis response for Twitter."""
    logging.debug(f"Formatting response with: requester={requester_username}, "
                f"original_poster={original_poster_username}, is_root={is_root_tweet}")
        
    prefix = f"@{requester_username} " if requester_username else ""
    
    source_note = (
        f"Analyzing image from @{original_poster_username}\n"
        if is_root_tweet and original_poster_username else ""
    )
    
    logging.debug(f"Generated source note: '{source_note}'")
    
    result = "AI-Generated" if is_ai else "Not AI-Generated"
    confidence_text = f"({confidence}% confidence {'of AI' if is_ai else 'of AI'})"
    
    github_link = "\nhttps://github.com/BitMind-AI/bitmind-subnet"

    return (
        f"{prefix}{source_note}"
        f"📊 SYNTHETIC MEDIA ANALYSIS REPORT\n"
        f"Status: {result} {'🤖' if is_ai else '👤'}\n"
        f"Confidence of AI-Generation: {confidence}%\n"
        f"Network: SN34 (BitMind)\n"
        f"{github_link}"
    )


def extract_image_url(tweet_data: Dict) -> tuple[Optional[str], bool]:
    """
    Extract image URL from tweet data with validation.
    Returns tuple of (url, is_from_root_tweet).
    """
    if not isinstance(tweet_data, dict):
        logging.error("Invalid tweet data format")
        return None, False

    try:
        logging.debug(f"Extracting image URL from tweet data structure: {tweet_data.keys()}")
        
        # First check if this is the root tweet or a reply
        is_root_tweet = False
        if 'data' in tweet_data:
            is_root_tweet = not bool(tweet_data['data'].get('referenced_tweets', []))
            logging.debug(f"Is root tweet: {is_root_tweet}")
        
        # Check for media in current tweet's attachments first
        if 'data' in tweet_data:
            logging.debug(f"Checking data section: {tweet_data['data'].keys()}")
            attachments = tweet_data['data'].get('attachments', {})
            media_keys = attachments.get('media_keys', [])
            logging.debug(f"Found media keys in data: {media_keys}")
            
            if media_keys and 'includes' in tweet_data:
                media = tweet_data['includes'].get('media', [])
                logging.debug(f"Looking for media keys {media_keys} in includes media: {media}")
                
                for item in media:
                    if not isinstance(item, dict):
                        continue
                    
                    if item.get('media_key') in media_keys:
                        media_type = item.get('type')
                        logging.debug(f"Found matching media item type: {media_type}")
                        
                        if media_type == 'photo':
                            url = item.get('url')
                            if url:
                                logging.debug(f"Found photo URL in current tweet: {url}")
                                return url, is_root_tweet
                        elif media_type in ('video', 'animated_gif'):
                            url = item.get('preview_image_url')
                            if url:
                                logging.debug(f"Found video/gif preview URL in current tweet: {url}")
                                return url, is_root_tweet

        logging.debug("No suitable image URL found after all checks")
        return None, False

    except Exception as e:
        logging.error(f"Error extracting image URL: {str(e)}")
        return None, False