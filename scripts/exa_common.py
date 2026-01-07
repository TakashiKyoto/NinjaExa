#!/usr/bin/env python3
"""
exa_common.py - Shared utilities for Exa search scripts

Supports two modes:
1. MCP Mode (default): Uses Exa's hosted MCP endpoint - NO API KEY for basic tools
2. Direct API Mode: Uses api.exa.ai - Requires EXA_API_KEY, enables ALL features

Advanced features (category, domains, dates, findSimilar, highlights, summary)
require Direct API Mode with EXA_API_KEY.

Rate Limiting:
All API calls are rate-limited to prevent abuse. See exa_rate_limiter.py for details.
Default limits: 15/min, 60/10min, 200/hour, 1000/day. Override via NINJAEXA_RATE_* env vars.
"""

import json
import urllib.request
import urllib.error
import ssl
import sys
import os
import io
import time
from typing import Optional, Dict, Any, List

# Import rate limiter (local module)
try:
    from exa_rate_limiter import check_rate_limit, record_request
except ImportError:
    # Fallback if rate limiter not available (shouldn't happen but be safe)
    def check_rate_limit():
        return (True, 0.0, None)
    def record_request():
        pass

# =============================================================================
# Fix Windows console encoding (per CLAUDE.md - avoid Unicode issues)
# =============================================================================

# Force UTF-8 output on Windows to avoid encoding errors
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# =============================================================================
# Configuration
# =============================================================================

# MCP endpoint (free, limited features)
EXA_MCP_BASE_URL = "https://mcp.exa.ai/mcp"

# Direct API endpoints (requires API key, full features)
EXA_API_BASE_URL = "https://api.exa.ai"
EXA_API_SEARCH = f"{EXA_API_BASE_URL}/search"
EXA_API_FIND_SIMILAR = f"{EXA_API_BASE_URL}/findSimilar"
EXA_API_CONTENTS = f"{EXA_API_BASE_URL}/contents"

DEFAULT_TIMEOUT = 30  # seconds

# Tools available without API key (MCP mode)
FREE_TOOLS = {"web_search_exa", "get_code_context_exa"}

# Tools requiring API key
PREMIUM_TOOLS = {
    "deep_search_exa",
    "crawling_exa",
    "company_research_exa",
    "linkedin_search_exa",
    "deep_researcher_start",
    "deep_researcher_check"
}

# Valid categories for search filtering
VALID_CATEGORIES = {
    "company", "research paper", "news", "pdf", "github",
    "tweet", "personal site", "linkedin profile", "financial report"
}

# =============================================================================
# API Key Management (Smart Fallback with Caching)
# =============================================================================

# Cache location for discovered API key
_API_KEY_CACHE_FILE = os.path.join(os.path.expanduser("~"), ".cache", "ninjaexa_api_key")
_API_KEY_CACHE_HOURS = 24


def _search_bash_files_for_key() -> Optional[str]:
    """
    Search ~/.bash/*.sh files for EXA_API_KEY export (Linux/WSL).

    Returns:
        API key if found, None otherwise
    """
    import glob
    import re

    bash_dir = os.path.join(os.path.expanduser("~"), ".bash")
    if not os.path.isdir(bash_dir):
        return None

    # Pattern matches: export EXA_API_KEY="value" or EXA_API_KEY='value' or EXA_API_KEY=value
    pattern = re.compile(r'(?:export\s+)?EXA_API_KEY\s*=\s*["\']?([a-zA-Z0-9_-]+)["\']?')

    for sh_file in glob.glob(os.path.join(bash_dir, "*.sh")):
        try:
            with open(sh_file, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # Skip comments
                    line_stripped = line.strip()
                    if line_stripped.startswith('#'):
                        continue
                    match = pattern.search(line)
                    if match:
                        return match.group(1)
        except (IOError, OSError):
            continue

    return None


def _search_powershell_profiles_for_key() -> Optional[str]:
    """
    Search PowerShell profile files for EXA_API_KEY (Windows).

    Checks both PowerShell 5 and PowerShell 7 profiles:
    - PS5: Documents/WindowsPowerShell/Microsoft.PowerShell_profile.ps1
    - PS7: Documents/PowerShell/Microsoft.PowerShell_profile.ps1

    Returns:
        API key if found, None otherwise
    """
    import re

    # Only run on Windows
    if sys.platform != 'win32':
        return None

    home = os.path.expanduser("~")
    profile_paths = [
        # PowerShell 5
        os.path.join(home, "Documents", "WindowsPowerShell", "Microsoft.PowerShell_profile.ps1"),
        # PowerShell 7
        os.path.join(home, "Documents", "PowerShell", "Microsoft.PowerShell_profile.ps1"),
    ]

    # Pattern matches: $env:EXA_API_KEY = "value" or $env:EXA_API_KEY = 'value'
    pattern = re.compile(r'\$env:EXA_API_KEY\s*=\s*["\']([a-zA-Z0-9_-]+)["\']')

    for profile_path in profile_paths:
        if not os.path.exists(profile_path):
            continue
        try:
            with open(profile_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    # Skip comments
                    line_stripped = line.strip()
                    if line_stripped.startswith('#'):
                        continue
                    match = pattern.search(line)
                    if match:
                        return match.group(1)
        except (IOError, OSError):
            continue

    return None


def _read_cached_key() -> Optional[str]:
    """Read API key from cache if valid (< 24 hours old)."""
    import time

    if not os.path.exists(_API_KEY_CACHE_FILE):
        return None

    try:
        mtime = os.path.getmtime(_API_KEY_CACHE_FILE)
        age_hours = (time.time() - mtime) / 3600

        if age_hours >= _API_KEY_CACHE_HOURS:
            return None  # Cache expired

        with open(_API_KEY_CACHE_FILE, 'r') as f:
            cached_key = f.read().strip()
            return cached_key if cached_key else None
    except (IOError, OSError):
        return None


def _write_cached_key(key: str) -> None:
    """Cache API key for 24 hours."""
    try:
        cache_dir = os.path.dirname(_API_KEY_CACHE_FILE)
        os.makedirs(cache_dir, exist_ok=True)
        with open(_API_KEY_CACHE_FILE, 'w') as f:
            f.write(key)
    except (IOError, OSError):
        pass  # Cache write failed, not critical


def get_api_key() -> Optional[str]:
    """
    Get Exa API key with smart fallback:

    1. Check environment variable EXA_API_KEY (fastest)
    2. Check 24-hour cache file
    3. Search config files:
       - Linux/WSL: ~/.bash/*.sh files
       - Windows: PowerShell profile files (PS5 and PS7)

    Found keys are cached for 24 hours to avoid repeated file searches.

    Returns:
        API key string or None if not found
    """
    # 1. Check environment first (fastest path)
    key = os.environ.get("EXA_API_KEY")
    if key:
        return key

    # 2. Check cache (valid for 24 hours)
    cached_key = _read_cached_key()
    if cached_key:
        return cached_key

    # 3. Search config files (platform-specific)
    found_key = None

    # Try Linux/WSL bash files
    found_key = _search_bash_files_for_key()

    # Try Windows PowerShell profiles
    if not found_key:
        found_key = _search_powershell_profiles_for_key()

    if found_key:
        _write_cached_key(found_key)
        return found_key

    return None


def get_mcp_url(tool_name: str) -> str:
    """
    Get the appropriate MCP URL based on tool and API key availability.

    For premium tools, appends API key and tool enablement to URL.

    Args:
        tool_name: Name of the tool being called

    Returns:
        Full MCP URL to use
    """
    api_key = get_api_key()

    # Free tools work without modifications
    if tool_name in FREE_TOOLS:
        return EXA_MCP_BASE_URL

    # Premium tools need API key in URL
    if api_key:
        # Enable the specific tool and pass API key
        return f"{EXA_MCP_BASE_URL}?exaApiKey={api_key}&tools={tool_name}"

    # No API key - will fail but let the error propagate with helpful message
    return EXA_MCP_BASE_URL


def is_premium_tool(tool_name: str) -> bool:
    """Check if tool requires API key."""
    return tool_name in PREMIUM_TOOLS


# =============================================================================
# Rate Limiting Integration
# =============================================================================

def _apply_rate_limit() -> None:
    """
    Check rate limit and apply delay if needed.
    Raises Exception if request is blocked.
    """
    allowed, delay, message = check_rate_limit()
    
    if not allowed:
        # Hard block - raise exception with helpful message
        raise Exception(message)
    
    if message:
        # Warning or cooldown message - print to stderr
        print(f"{message}", file=sys.stderr)
    
    if delay > 0:
        # Apply delay before proceeding
        time.sleep(delay)


# =============================================================================
# HTTP Client (stdlib only - no dependencies)
# =============================================================================

def make_mcp_request(tool_name: str, arguments: Dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> str:
    """
    Make a JSON-RPC 2.0 request to Exa's MCP endpoint.

    Args:
        tool_name: Tool name (e.g., 'web_search_exa', 'deep_search_exa')
        arguments: Tool-specific arguments
        timeout: Request timeout in seconds

    Returns:
        The text content from the response

    Raises:
        Exception on network errors, timeouts, invalid responses, or rate limit exceeded
    """
    # Check rate limit before making request
    _apply_rate_limit()
    
    # Get appropriate URL based on tool and API key
    mcp_url = get_mcp_url(tool_name)

    # Build JSON-RPC 2.0 request
    request_body = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }

    # Prepare request
    data = json.dumps(request_body).encode('utf-8')
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "User-Agent": "Claude-Code-Exa-Skill/1.0"
    }

    req = urllib.request.Request(mcp_url, data=data, headers=headers, method='POST')

    # Create SSL context (for HTTPS)
    ssl_context = ssl.create_default_context()

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as response:
            response_text = response.read().decode('utf-8')
            result = parse_sse_response(response_text)
            # Record successful request for rate limiting
            record_request()
            return result

    except urllib.error.URLError as e:
        if hasattr(e, 'reason'):
            raise Exception(f"Network error: {e.reason}")
        elif hasattr(e, 'code'):
            raise Exception(f"HTTP error {e.code}: {e.read().decode('utf-8', errors='replace')}")
        else:
            raise Exception(f"URL error: {e}")

    except TimeoutError:
        raise Exception(f"Request timed out after {timeout} seconds. Try using --type fast for quicker results.")


def parse_sse_response(response_text: str) -> str:
    """
    Parse Server-Sent Events (SSE) response format.

    Exa MCP returns SSE format:
        data: {"jsonrpc":"2.0","result":{"content":[{"type":"text","text":"..."}]}}

    Args:
        response_text: Raw response text

    Returns:
        Extracted text content

    Raises:
        Exception if parsing fails
    """
    lines = response_text.strip().split('\n')

    for line in lines:
        if line.startswith('data: '):
            try:
                data = json.loads(line[6:])  # Skip "data: " prefix

                # Check for errors
                if 'error' in data:
                    error = data['error']
                    error_code = error.get('code', '')
                    error_msg = error.get('message', 'Unknown error')
                    raise Exception(f"MCP error {error_code}: {error_msg}")

                # Extract content
                if 'result' in data and 'content' in data['result']:
                    content = data['result']['content']
                    if content and len(content) > 0:
                        return content[0].get('text', '')

            except json.JSONDecodeError:
                continue  # Try next line

    # If we reach here, no valid data was found
    raise Exception("No valid response data found. The search may have returned empty results.")


# =============================================================================
# Output Formatting
# =============================================================================

def _truncate_at_sentence(text: str, max_chars: int = 500) -> str:
    """
    Truncate text at a sentence boundary near max_chars.

    Instead of hard-cutting at exactly max_chars (which can split mid-word
    or mid-sentence), this finds the last complete sentence within the limit.

    Falls back to hard truncation if no sentence boundary found.

    Args:
        text: Text to truncate
        max_chars: Target maximum characters (will be slightly flexible)

    Returns:
        Truncated text with "..." if shortened
    """
    import re

    text = text.strip()
    if len(text) <= max_chars:
        return text

    # Get text up to max_chars + small buffer for sentence completion
    search_text = text[:max_chars + 50]

    # Find sentence endings: period, exclamation, question mark followed by space or end
    # Also handle common abbreviations by requiring the next char to be uppercase or end
    sentence_end_pattern = re.compile(r'[.!?](?:\s+|$)')

    matches = list(sentence_end_pattern.finditer(search_text))

    if matches:
        # Find the last sentence boundary at or near max_chars
        best_end = None
        for match in matches:
            end_pos = match.end()
            # Accept if within max_chars, or slightly over if close to limit
            if end_pos <= max_chars:
                best_end = end_pos
            elif end_pos <= max_chars + 30 and best_end is None:
                # Allow slight overflow for first sentence if nothing else found
                best_end = end_pos

        if best_end and best_end >= max_chars * 0.5:  # At least 50% of target
            return text[:best_end].strip()

    # No good sentence boundary - fall back to word boundary
    truncated = text[:max_chars]
    last_space = truncated.rfind(' ')
    if last_space > max_chars * 0.7:  # Don't go too far back
        return truncated[:last_space].strip() + "..."

    return truncated.strip() + "..."


def format_results(query: str, results_text: str, tool_type: str = "web") -> str:
    """
    Format search results for AI-friendly output.

    Args:
        query: Original search query
        results_text: Raw results from Exa
        tool_type: "web", "code", or "deep"

    Returns:
        Formatted string output
    """
    titles = {
        "web": "Web Search",
        "code": "Code Search",
        "deep": "Deep Research"
    }
    title = titles.get(tool_type, "Search")

    output = []
    output.append(f"=== Exa {title} Results ===")
    output.append(f"Query: {query}")
    output.append("")

    if results_text:
        output.append(results_text)
    else:
        output.append("No results found. Try:")
        output.append("  - Using more specific search terms")
        output.append("  - Including relevant keywords (language, framework, etc.)")
        output.append("  - Checking for spelling errors")

    output.append("")
    return '\n'.join(output)


def print_error(message: str):
    """Print error message to stderr."""
    print(f"[ERROR] {message}", file=sys.stderr)


def print_info(message: str):
    """Print info message to stderr (for debugging)."""
    print(f"[INFO] {message}", file=sys.stderr)


# =============================================================================
# Direct Exa API (Full Features - Requires API Key)
# =============================================================================

def make_direct_api_request(
    endpoint: str,
    params: Dict[str, Any],
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Make a direct request to Exa API (not MCP).

    This enables ALL Exa features including:
    - Category filtering (github, research paper, news, etc.)
    - Domain filtering (include/exclude)
    - Date filtering (published date, crawl date)
    - Highlights and summaries
    - FindSimilar

    Args:
        endpoint: Full API endpoint URL (e.g., EXA_API_SEARCH)
        params: Request parameters (will be JSON-encoded)
        timeout: Request timeout in seconds

    Returns:
        Parsed JSON response as dict

    Raises:
        Exception if API key not set, request fails, or rate limit exceeded
    """
    # Check rate limit before making request
    _apply_rate_limit()
    
    api_key = get_api_key()
    if not api_key:
        raise Exception(
            "EXA_API_KEY not set. Direct API features require an API key.\n"
            "Get one at https://exa.ai and set: export EXA_API_KEY='your-key'"
        )

    # Prepare request
    data = json.dumps(params).encode('utf-8')
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "x-api-key": api_key
    }

    req = urllib.request.Request(endpoint, data=data, headers=headers, method='POST')
    ssl_context = ssl.create_default_context()

    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context) as response:
            response_text = response.read().decode('utf-8')
            result = json.loads(response_text)
            # Record successful request for rate limiting
            record_request()
            return result

    except urllib.error.HTTPError as e:
        error_body = e.read().decode('utf-8', errors='replace')
        try:
            error_json = json.loads(error_body)
            error_msg = error_json.get('error', error_body)
        except:
            error_msg = error_body
        raise Exception(f"Exa API error ({e.code}): {error_msg}")

    except urllib.error.URLError as e:
        raise Exception(f"Network error: {e.reason}")

    except TimeoutError:
        raise Exception(f"Request timed out after {timeout} seconds")


def direct_search(
    query: str,
    num_results: int = 10,
    search_type: str = "auto",
    category: Optional[str] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    start_published_date: Optional[str] = None,
    end_published_date: Optional[str] = None,
    include_text: Optional[List[str]] = None,
    exclude_text: Optional[List[str]] = None,
    use_highlights: bool = False,
    highlights_per_url: int = 1,
    num_sentences: int = 3,
    use_summary: bool = False,
    livecrawl: str = "fallback",
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Perform advanced search using direct Exa API.

    This provides full access to all Exa features.

    Args:
        query: Search query
        num_results: Number of results (1-100)
        search_type: 'auto', 'keyword', or 'neural'
        category: Filter by category (company, github, news, research paper, etc.)
        include_domains: Only include results from these domains
        exclude_domains: Exclude results from these domains
        start_published_date: Only results published after this date (ISO 8601)
        end_published_date: Only results published before this date (ISO 8601)
        include_text: Results must contain these phrases
        exclude_text: Results must NOT contain these phrases
        use_highlights: Return AI-selected relevant snippets
        highlights_per_url: Number of highlight snippets per result
        num_sentences: Sentences per highlight
        use_summary: Return AI-generated summary per result
        livecrawl: 'never', 'fallback', 'preferred', 'always'
        timeout: Request timeout

    Returns:
        Full Exa API response as dict
    """
    params: Dict[str, Any] = {
        "query": query,
        "numResults": min(100, max(1, num_results)),
        "type": search_type,
    }

    # Category filter
    if category and category.lower() in VALID_CATEGORIES:
        params["category"] = category.lower()

    # Domain filters
    if include_domains:
        params["includeDomains"] = include_domains
    if exclude_domains:
        params["excludeDomains"] = exclude_domains

    # Date filters (ISO 8601 format)
    if start_published_date:
        params["startPublishedDate"] = start_published_date
    if end_published_date:
        params["endPublishedDate"] = end_published_date

    # Text filters
    if include_text:
        params["includeText"] = include_text[:1]  # Max 1 allowed
    if exclude_text:
        params["excludeText"] = exclude_text[:1]  # Max 1 allowed

    # Contents options
    contents = {}

    # Always get text
    contents["text"] = True

    # Highlights
    if use_highlights:
        contents["highlights"] = {
            "numSentences": num_sentences,
            "highlightsPerUrl": highlights_per_url
        }

    # Summary
    if use_summary:
        contents["summary"] = True

    # Livecrawl
    if livecrawl in ("never", "fallback", "preferred", "always"):
        contents["livecrawl"] = livecrawl

    if contents:
        params["contents"] = contents

    return make_direct_api_request(EXA_API_SEARCH, params, timeout)


def find_similar(
    url: str,
    num_results: int = 10,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    exclude_source_domain: bool = True,
    start_published_date: Optional[str] = None,
    end_published_date: Optional[str] = None,
    category: Optional[str] = None,
    use_highlights: bool = False,
    use_summary: bool = False,
    timeout: int = DEFAULT_TIMEOUT
) -> Dict[str, Any]:
    """
    Find content similar to a given URL.

    Uses neural embeddings to find conceptually similar pages.
    Great for: competitor analysis, research expansion, finding alternatives.

    Args:
        url: URL to find similar content for
        num_results: Number of results (1-100)
        include_domains: Only include results from these domains
        exclude_domains: Exclude results from these domains
        exclude_source_domain: Exclude the source URL's domain from results
        start_published_date: Only results published after this date
        end_published_date: Only results published before this date
        category: Filter by category
        use_highlights: Return AI-selected snippets
        use_summary: Return AI-generated summary
        timeout: Request timeout

    Returns:
        Exa findSimilar response
    """
    params: Dict[str, Any] = {
        "url": url,
        "numResults": min(100, max(1, num_results)),
        "excludeSourceDomain": exclude_source_domain
    }

    if category and category.lower() in VALID_CATEGORIES:
        params["category"] = category.lower()

    if include_domains:
        params["includeDomains"] = include_domains
    if exclude_domains:
        params["excludeDomains"] = exclude_domains

    if start_published_date:
        params["startPublishedDate"] = start_published_date
    if end_published_date:
        params["endPublishedDate"] = end_published_date

    # Contents
    contents = {"text": True}
    if use_highlights:
        contents["highlights"] = {"numSentences": 3, "highlightsPerUrl": 2}
    if use_summary:
        contents["summary"] = True

    params["contents"] = contents

    return make_direct_api_request(EXA_API_FIND_SIMILAR, params, timeout)


def format_api_results(response: Dict[str, Any], query_or_url: str, result_type: str = "search") -> str:
    """
    Format direct API response for AI-friendly output.

    Args:
        response: Raw API response dict
        query_or_url: Original query or URL
        result_type: 'search' or 'similar'

    Returns:
        Formatted string output
    """
    output = []

    if result_type == "similar":
        output.append("=== Exa Find Similar Results ===")
        output.append(f"Similar to: {query_or_url}")
    else:
        output.append("=== Exa Search Results ===")
        output.append(f"Query: {query_or_url}")

    results = response.get("results", [])
    output.append(f"Found: {len(results)} results")

    # Cost info if available
    if "costDollars" in response:
        cost = response.get("costDollars", {})
        if isinstance(cost, dict):
            total = cost.get("total", 0)
            output.append(f"Cost: ${total:.4f}")

    output.append("")

    if not results:
        output.append("No results found.")
        return '\n'.join(output)

    for i, result in enumerate(results, 1):
        output.append(f"--- Result {i} ---")

        title = result.get("title", "No title")
        url = result.get("url", "")
        published = result.get("publishedDate", "")

        output.append(f"Title: {title}")
        output.append(f"URL: {url}")
        if published:
            output.append(f"Published: {published[:10]}")  # Just date part

        # Summary (if available)
        summary = result.get("summary")
        if summary:
            output.append(f"Summary: {summary}")

        # Highlights (if available)
        highlights = result.get("highlights", [])
        if highlights:
            output.append("Highlights:")
            for h in highlights[:3]:  # Max 3 highlights
                output.append(f"  - {h}")

        # Text excerpt (if no highlights/summary)
        if not summary and not highlights:
            text = result.get("text", "")
            if text:
                # Show first ~500 chars, but try to end at sentence boundary
                excerpt = _truncate_at_sentence(text, max_chars=500)
                output.append(f"Content: {excerpt}")

        output.append("")

    return '\n'.join(output)


def has_api_key() -> bool:
    """Check if EXA_API_KEY is available."""
    return bool(get_api_key())
