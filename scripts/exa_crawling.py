#!/usr/bin/env python3
"""
exa_crawling.py - Extract content from specific URLs using Exa AI

Uses Exa's hosted MCP endpoint - NO API KEY REQUIRED for basic usage.
Fetches and extracts clean content from URLs, bypassing many common blockers.

Why use this over regular web fetch:
- Works on Cloudflare-protected sites (uses Exa's pre-crawled cache)
- Bypasses many paywalls (if content was cached before paywall)
- Handles JS-heavy sites (pre-rendered content)
- Extracts clean text from PDFs
- No rate limiting on your end

Usage:
    python exa_crawling.py "https://example.com/article"
    python exa_crawling.py "https://arxiv.org/abs/2301.00001"

Examples:
    python exa_crawling.py "https://react.dev/blog/2024/04/25/react-19"
    python exa_crawling.py "https://github.com/anthropics/claude-code/blob/main/README.md"
    python exa_crawling.py "https://arxiv.org/pdf/2301.00001.pdf"
"""

import argparse
import sys
import os
import re

# Add script directory to path for local imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from exa_common import make_mcp_request, print_error, print_info

# =============================================================================
# Constants
# =============================================================================

TOOL_NAME = "crawling_exa"
DEFAULT_TIMEOUT = 30

# Note: crawling_exa requires the tool to be enabled on the MCP endpoint.
# The default hosted endpoint only has web_search_exa and get_code_context_exa.
# This tool may require API key or explicit tool enablement.

# =============================================================================
# URL Validation
# =============================================================================

def is_valid_url(url: str) -> bool:
    """
    Basic URL validation.

    Args:
        url: URL string to validate

    Returns:
        True if URL looks valid, False otherwise
    """
    # Basic pattern: protocol://domain/path
    pattern = r'^https?://[^\s/$.?#].[^\s]*$'
    return bool(re.match(pattern, url, re.IGNORECASE))


def normalize_url(url: str) -> str:
    """
    Normalize URL - ensure https:// prefix.

    Args:
        url: URL string (may or may not have protocol)

    Returns:
        URL with https:// prefix
    """
    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
    return url


# =============================================================================
# Main Crawl Function
# =============================================================================

def crawl_url(url: str) -> str:
    """
    Extract content from a specific URL using Exa AI.

    Advantages over regular web fetching:
    - Uses Exa's pre-crawled cache - works on sites that block bots
    - Cloudflare-protected sites often work
    - JS-heavy sites already rendered
    - PDF content extraction
    - Clean text output (no HTML noise)

    Args:
        url: Full URL to extract content from

    Returns:
        Extracted text content from the URL

    Raises:
        Exception on errors or invalid URL
    """
    # Normalize and validate URL
    url = normalize_url(url)
    if not is_valid_url(url):
        raise Exception(f"Invalid URL format: {url}")

    # Build arguments for Exa MCP crawling_exa tool
    arguments = {
        "url": url
    }

    # Make request
    results_text = make_mcp_request(TOOL_NAME, arguments, timeout=DEFAULT_TIMEOUT)

    # Format output
    output = []
    output.append("=== Exa URL Content Extraction ===")
    output.append(f"URL: {url}")
    output.append("")

    if results_text:
        output.append(results_text)
    else:
        output.append("[WARNING] No content extracted from URL.")
        output.append("Possible reasons:")
        output.append("  - URL not in Exa's cache")
        output.append("  - Site blocks all crawlers")
        output.append("  - Content behind login/paywall")
        output.append("  - URL may be incorrect")

    output.append("")
    return '\n'.join(output)


# =============================================================================
# CLI Interface
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Extract content from URLs using Exa AI (bypasses many blockers)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Why use Exa crawling over regular web fetch:
  - Works on Cloudflare/bot-protected sites (uses cached content)
  - Handles JS-heavy sites (pre-rendered)
  - Extracts text from PDFs
  - No rate limiting issues

Examples:
  %(prog)s "https://react.dev/blog/2024/04/25/react-19"
  %(prog)s "https://github.com/user/repo/blob/main/README.md"
  %(prog)s "https://arxiv.org/pdf/2301.00001.pdf"
  %(prog)s "https://news.ycombinator.com/item?id=12345"

Supported content types:
  - Web pages (HTML)
  - PDF documents
  - GitHub files (rendered)
  - News articles
  - Blog posts
  - Documentation pages

Note: Content must be in Exa's pre-crawled index. Very new or private
pages may not be available.
        """
    )

    parser.add_argument(
        "url",
        help="URL to extract content from (https:// prefix optional)"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    try:
        results = crawl_url(url=args.url)
        print(results)
        return 0

    except Exception as e:
        error_msg = str(e)
        print_error(error_msg)

        # Provide helpful message if tool not found
        if "not found" in error_msg.lower() or "-32602" in error_msg:
            print_info("")
            print_info("crawling_exa requires Exa API key or explicit tool enablement.")
            print_info("The free MCP endpoint only includes: web_search_exa, get_code_context_exa")
            print_info("")
            print_info("Alternatives:")
            print_info("  1. Use Claude's WebFetch tool (may be blocked on some sites)")
            print_info("  2. Get an Exa API key from https://exa.ai and set EXA_API_KEY env var")

        return 1


if __name__ == "__main__":
    sys.exit(main())
