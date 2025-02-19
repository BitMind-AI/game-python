# Bittensor Plugin for GAME SDK

A plugin for interacting with Bittensor subnets through the GAME SDK. Currently supports image detection using subnet 34 (BitMind).

## Installation

```bash
pip install game-sdk
pip install -e plugins/bittensor
```

## Configuration

Set up your environment variables in a `.env` file:

```env
# Game SDK credentials
GAME_API_KEY=your_game_api_key

# Twitter API credentials (required for examples)
TWITTER_BEARER_TOKEN=your_bearer_token
TWITTER_API_KEY=your_api_key
TWITTER_API_SECRET_KEY=your_api_secret
TWITTER_ACCESS_TOKEN=your_access_token
TWITTER_ACCESS_TOKEN_SECRET=your_access_secret
TWITTER_CLIENT_KEY=your_client_key
TWITTER_CLIENT_SECRET=your_client_secret
```

## Usage

```python
from bittensor_game_sdk.bittensor_plugin import BittensorPlugin
# Initialize plugin
plugin = BittensorPlugin()
# Detect if an image is AI-generated
result = plugin.call_subnet(34, {"image": "https://example.com/image.jpg"})
print(f"Is AI: {result.get('isAI')}")
print(f"Confidence: {result.get('confidence')}%")
```

## Examples

The repository includes two main examples demonstrating different approaches to image analysis:

### 1. Worker Example (bittensor_worker.py)

A standalone worker that can analyze individual tweets for AI-generated images:

```bash
python plugins/bittensor/examples/bittensor_worker.py
```

Features:
- Direct image analysis from tweet URLs
- Rate limiting for both Twitter and Bittensor APIs
- Response caching to improve performance
- Comprehensive error tracking and logging
- Handles both direct tweets and reply chains
- Formats responses with source attribution

### 2. Agent Example (bittensor_agent.py)

A continuous monitoring agent that processes Twitter mentions:

```bash
python plugins/bittensor/examples/bittensor_agent.py
```

Features:
- Monitors Twitter mentions every 30 minutes
- 60-minute lookback window to prevent missing mentions
- Processes up to 5 mentions per check
- Uses the worker for image analysis
- Handles Twitter API rate limits
- Provides detailed processing statistics
- Runs as a daemon thread for continuous operation

## API Reference

### BittensorPlugin

Main plugin class for interacting with Bittensor subnets.

Methods:
- `call_subnet(subnet_id: int, payload: Dict)`: Call a specific subnet
- `detect_image(img_url: str)`: Detect if an image is AI-generated
- `get_subnet_info(subnet_id: int)`: Get information about a subnet
- `list_subnets()`: List available subnets

### BittensorImageWorker

Worker implementation for image detection.

Methods:
- `detect_image(tweet_id: str)`: Analyze images in a tweet
- `run(tweet_id: str)`: Process a single tweet
- `_post_twitter_reply(tweet_id: str, response: str)`: Post analysis results

### Utils

Helper modules for the worker and agent:
- `rate_limiting.py`: API rate limit management
- `cache.py`: Response caching system
- `formatters.py`: Response formatting utilities
- `logging.py`: Performance tracking and error logging