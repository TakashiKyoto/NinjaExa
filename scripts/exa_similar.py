#!/usr/bin/env python3
"""
exa_similar.py - Find similar content using Exa AI

Uses neural embeddings to find content conceptually similar to a given URL.
REQUIRES EXA_API_KEY environment variable.

Use cases:
- Competitor analysis: Find companies similar to a target
- Research expansion: Find related papers/articles
- Content discovery: Find similar tutorials, guides, documentation
- Alternative finding: Find alternatives to a tool/library

Usage:
    python exa_similar.py "https://example.com/page"
    python exa_similar.py "https://github.com/org/repo" --num-results 15
    python exa_similar.py "https://company.com" --category company
    python exa_similar.py "url" --exclude-source  # Exclude same domain

Examples:
    python exa_similar.py "https://cursor.sh" --category company
    python exa_similar.py "https://arxiv.org/abs/2301.00001" --category "research paper"
    python exa_similar.py "https://react.dev" --include-domains github.com,npmjs.com
"""

import argparse
import sys
import os
from datetime import datetime, timedelta

# Add script directory to path for local imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from exa_common import (
    find_similar, format_api_results, print_error, print_info,
    has_api_key, VALID_CATEGORIES
)


# =============================================================================
# CLI Interface
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    categories_list = ", ".join(sorted(VALID_CATEGORIES))

    parser = argparse.ArgumentParser(
        description="Find similar content using Exa AI neural embeddings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Use Cases:
  Competitor Analysis:
    %(prog)s "https://cursor.sh" --category company --num-results 10

  Research Expansion:
    %(prog)s "https://arxiv.org/abs/2301.00001" --category "research paper"

  Find Alternatives:
    %(prog)s "https://github.com/prisma/prisma" --category github

  Content Discovery:
    %(prog)s "https://react.dev/learn/tutorial-tic-tac-toe"

Available Categories:
  {categories_list}

Examples:
  %(prog)s "https://openai.com" --category company
  %(prog)s "https://github.com/anthropics/claude-code" --category github
  %(prog)s "https://stripe.com/docs/api" --highlights --summary
  %(prog)s "https://example.com" --days 90  # Only content from last 90 days

NOTE: Requires EXA_API_KEY environment variable.
        """
    )

    parser.add_argument(
        "url",
        help="URL to find similar content for"
    )

    parser.add_argument(
        "--num-results", "-n",
        type=int,
        default=10,
        help="Number of results (1-100, default: 10)"
    )

    parser.add_argument(
        "--category", "-c",
        choices=list(VALID_CATEGORIES),
        help="Filter results by category"
    )

    parser.add_argument(
        "--include-domains",
        type=str,
        help="Comma-separated domains to include (e.g., github.com,stackoverflow.com)"
    )

    parser.add_argument(
        "--exclude-domains",
        type=str,
        help="Comma-separated domains to exclude"
    )

    parser.add_argument(
        "--exclude-source",
        action="store_true",
        default=True,
        help="Exclude source URL's domain from results (default: true)"
    )

    parser.add_argument(
        "--include-source",
        action="store_true",
        help="Include source URL's domain in results"
    )

    parser.add_argument(
        "--days",
        type=int,
        help="Only include content published within last N days"
    )

    parser.add_argument(
        "--start-date",
        type=str,
        help="Only content published after this date (YYYY-MM-DD)"
    )

    parser.add_argument(
        "--end-date",
        type=str,
        help="Only content published before this date (YYYY-MM-DD)"
    )

    parser.add_argument(
        "--highlights",
        action="store_true",
        help="Include AI-selected relevant snippets"
    )

    parser.add_argument(
        "--summary",
        action="store_true",
        help="Include AI-generated summary per result"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Check API key
    if not has_api_key():
        print_error("EXA_API_KEY not set. FindSimilar requires an API key.")
        print_info("Get one at https://exa.ai and set: export EXA_API_KEY='your-key'")
        return 1

    # Parse domain filters
    include_domains = None
    exclude_domains = None

    if args.include_domains:
        include_domains = [d.strip() for d in args.include_domains.split(",")]

    if args.exclude_domains:
        exclude_domains = [d.strip() for d in args.exclude_domains.split(",")]

    # Handle date filtering
    start_date = args.start_date
    end_date = args.end_date

    if args.days and not start_date:
        # Calculate start date from days
        start_dt = datetime.now() - timedelta(days=args.days)
        start_date = start_dt.strftime("%Y-%m-%dT00:00:00.000Z")

    # Handle exclude source domain
    exclude_source = args.exclude_source
    if args.include_source:
        exclude_source = False

    try:
        response = find_similar(
            url=args.url,
            num_results=args.num_results,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            exclude_source_domain=exclude_source,
            start_published_date=start_date,
            end_published_date=end_date,
            category=args.category,
            use_highlights=args.highlights,
            use_summary=args.summary
        )

        output = format_api_results(response, args.url, result_type="similar")
        print(output)
        return 0

    except Exception as e:
        print_error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
