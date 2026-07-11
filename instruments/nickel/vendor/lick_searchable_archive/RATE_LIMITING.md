# Rate Limiting Guide

The Lick Archive Client has been enhanced to handle rate limiting (HTTP 429 errors) more gracefully.

## Features

### 1. Automatic Retry on 429 Errors

The client now automatically retries requests when encountering 429 (Too Many Requests) errors, using:
- Exponential backoff (starting at 5s, up to configurable max)
- Respect for server's `Retry-After` header when provided
- Configurable retry timeouts

### 2. Built-in Rate Limiting

To prevent 429 errors from occurring in the first place, the client includes a configurable delay between requests.

### 3. Smart Request Handling

- Retries on 429 and 5xx server errors
- Retries on connection errors and timeouts
- Does NOT retry on 4xx client errors (except 429)
- Preserves your session between retries

## Usage

### Basic Usage with Default Settings

```python
from lick_archive import LickArchiveClient

# Default: 0.1s delay between requests
client = LickArchiveClient("https://archive.ucolick.org/archive")

# Download multiple files - automatically rate limited
for filename in file_list:
    client.download(filename, f"/path/to/{filename}")
```

### Customizing Rate Limiting

```python
# More aggressive rate limiting (0.5s between requests)
client = LickArchiveClient(
    "https://archive.ucolick.org/archive",
    rate_limit_delay=0.5  # Wait 0.5 seconds between requests
)

# No rate limiting (not recommended for bulk downloads)
client = LickArchiveClient(
    "https://archive.ucolick.org/archive",
    rate_limit_delay=0.0  # No delay
)

# Conservative rate limiting for very large batch jobs
client = LickArchiveClient(
    "https://archive.ucolick.org/archive",
    rate_limit_delay=1.0  # Wait 1 second between requests
)
```

### Customizing Retry Behavior

```python
client = LickArchiveClient(
    "https://archive.ucolick.org/archive",
    retry_max_delay=30,      # Max 30s between retries (default: 10s)
    retry_max_time=300,      # Give up after 5 minutes (default: 60s)
    request_timeout=60,      # Wait up to 60s for response (default: 30s)
    rate_limit_delay=0.2     # 200ms between requests (default: 0.1s)
)
```

## Recommendations

### For Interactive/Small Queries
```python
# Use defaults - they're optimized for interactive use
client = LickArchiveClient("https://archive.ucolick.org/archive")
```

### For Moderate Batch Downloads (10-100 files)
```python
# Slightly more conservative
client = LickArchiveClient(
    "https://archive.ucolick.org/archive",
    rate_limit_delay=0.3,    # 300ms between requests
    retry_max_time=120       # Give it more time to retry
)
```

### For Large Batch Downloads (100+ files)
```python
# Be a good citizen - use conservative rate limiting
client = LickArchiveClient(
    "https://archive.ucolick.org/archive",
    rate_limit_delay=0.5,    # 500ms between requests
    retry_max_delay=60,      # Allow longer backoff delays
    retry_max_time=300       # Be patient with retries
)
```

### For Very Large Batch Operations (1000+ files)
```python
# Maximum politeness
client = LickArchiveClient(
    "https://archive.ucolick.org/archive",
    rate_limit_delay=1.0,    # 1 second between requests
    retry_max_delay=120,     # Up to 2 minutes between retries
    retry_max_time=600       # 10 minutes of retry time
)
```

## Understanding the Errors

### Before the Improvements

You would see:
```
[ERROR] Download failed for file.fits: 429 Client Error: Too Many Requests
```

The client would immediately fail without retrying.

### After the Improvements

You'll see informative warnings:
```
[WARNING] Rate limited (429) downloading file.fits. Server requested 60s delay.
[INFO] Downloading https://archive.ucolick.org/archive/data/file.fits
[INFO] Successfully downloaded 2048576 bytes to /path/to/file.fits
```

The client automatically handles the retry for you.

## Logging

Enable debug logging to see rate limiting in action:

```python
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger('lick_archive.client.lick_archive_client')
logger.setLevel(logging.DEBUG)

client = LickArchiveClient("https://archive.ucolick.org/archive")
```

You'll see messages like:
```
DEBUG:lick_archive.client.lick_archive_client:Rate limiting: sleeping for 0.082 seconds
DEBUG:lick_archive.client.lick_archive_client:Downloading https://archive.ucolick.org/archive/data/...
WARNING:lick_archive.client.lick_archive_client:Rate limited (429) downloading file.fits. Retrying with exponential backoff...
```

## Best Practices

1. **Start Conservative**: Use higher `rate_limit_delay` values for batch operations
2. **Monitor Your Logs**: Watch for 429 warnings - if you see many, increase your `rate_limit_delay`
3. **Be Patient**: Let the retry logic work - don't kill the script when you see warnings
4. **Use Sessions**: The client uses persistent sessions which are more efficient
5. **Parallelize Carefully**: If running multiple scripts, coordinate to avoid overwhelming the server

## Technical Details

### Retry Strategy
- Uses exponential backoff: 5s, 10s, 20s, ... up to `retry_max_delay`
- Total retry time limited by `retry_max_time`
- Honors server's `Retry-After` header when provided

### Rate Limiting Implementation
- Tracks time between requests per client instance
- Sleeps only the minimum necessary time
- Applied to all request types (query, header, download)

### What Gets Retried
- ✅ 429 Too Many Requests
- ✅ 500, 502, 503, 504 Server Errors
- ✅ Connection errors
- ✅ Timeout errors
- ❌ 400, 401, 403, 404 Client Errors (these won't succeed on retry)
