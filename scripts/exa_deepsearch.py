#!/usr/bin/env python3
"""
exa_deepsearch.py - Deep research search using Exa AI

Uses Exa's hosted MCP endpoint - NO API KEY REQUIRED for basic usage.
Provides intelligent query expansion and AI-generated summaries for comprehensive research.

Unlike regular web search with --type deep (which just searches more thoroughly),
deep_search_exa REWRITES your query intelligently and synthesizes results with summaries.

Usage:
    python exa_deepsearch.py "your research query"
    python exa_deepsearch.py "query" --num-results 15

Examples:
    python exa_deepsearch.py "React state management best practices 2025"
    python exa_deepsearch.py "microservices vs monolith tradeoffs"
    python exa_deepsearch.py "Python async programming patterns" --num-results 20
"""

import argparse
import sys
import os

# Add script directory to path for local imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from exa_common import make_mcp_request, format_results, print_error, print_info

# =============================================================================
# Constants
# =============================================================================

TOOL_NAME = "deep_search_exa"
DEFAULT_NUM_RESULTS = 10
DEFAULT_TIMEOUT = 45  # Deep search takes longer

# Note: deep_search_exa requires the tool to be enabled on the MCP endpoint.
# The default hosted endpoint only has web_search_exa and get_code_context_exa.
# This tool may require API key or explicit tool enablement.

# =============================================================================
# Main Search Function
# =============================================================================

def deep_search(
    query: str,
    num_results: int = DEFAULT_NUM_RESULTS
) -> str:
    """
    Perform deep research search using Exa AI.

    Unlike regular web_search_exa with type="deep", this tool:
    - Intelligently expands and rewrites your query for better results
    - Synthesizes information across multiple sources
    - Provides AI-generated summaries of findings
    - Better for research questions that need comprehensive answers

    Args:
        query: Research query text
        num_results: Number of results (1-50, default 10)

    Returns:
        Formatted search results with summaries

    Raises:
        Exception on errors
    """
    # Validate parameters
    num_results = max(1, min(50, num_results))

    # Build arguments for Exa MCP deep_search_exa tool
    # Note: deep_search_exa uses "objective" not "query"
    arguments = {
        "objective": query,
        "numResults": num_results
    }

    # Make request with longer timeout for deep search
    results_text = make_mcp_request(TOOL_NAME, arguments, timeout=DEFAULT_TIMEOUT)

    # Format output
    return format_results(query, results_text, tool_type="deep")


# =============================================================================
# CLI Interface
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Deep research search using Exa AI - query expansion + AI summaries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
How deep_search_exa differs from web_search --type deep:
  - web_search --type deep: Searches more thoroughly, returns raw results
  - deep_search_exa: REWRITES your query intelligently, SYNTHESIZES results

Examples:
  %(prog)s "React state management comparison 2025"
  %(prog)s "microservices architecture patterns" --num-results 15
  %(prog)s "Python vs Rust performance tradeoffs"
  %(prog)s "best practices for API design RESTful GraphQL"

Best for:
  - Research questions needing comprehensive answers
  - Topic comparisons and tradeoff analysis
  - Understanding complex technical concepts
  - Getting synthesized overview of a topic
        """
    )

    parser.add_argument(
        "query",
        help="Research query text (will be intelligently expanded)"
    )

    parser.add_argument(
        "--num-results", "-n",
        type=int,
        default=DEFAULT_NUM_RESULTS,
        help=f"Number of results to synthesize (1-50, default: {DEFAULT_NUM_RESULTS})"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    try:
        results = deep_search(
            query=args.query,
            num_results=args.num_results
        )
        print(results)
        return 0

    except Exception as e:
        error_msg = str(e)
        print_error(error_msg)

        # Provide helpful message if tool not found
        if "not found" in error_msg.lower() or "-32602" in error_msg:
            print_info("")
            print_info("deep_search_exa requires Exa API key or explicit tool enablement.")
            print_info("The free MCP endpoint only includes: web_search_exa, get_code_context_exa")
            print_info("")
            print_info("Alternatives:")
            print_info("  1. Use exa_websearch.py --type deep (similar but without AI summaries)")
            print_info("  2. Get an Exa API key from https://exa.ai and set EXA_API_KEY env var")

        return 1


if __name__ == "__main__":
    sys.exit(main())
