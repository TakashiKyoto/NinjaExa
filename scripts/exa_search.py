#!/usr/bin/env python3
"""
exa_search.py - Unified Smart Search using Exa AI

The RECOMMENDED script for most searches. Automatically:
- Detects query type (code, news, research, general)
- Selects appropriate search strategy
- Auto-suggests category when applicable
- Routes to best search method (MCP free or Direct API)

Supports all advanced features when EXA_API_KEY is set.

Usage:
    python exa_search.py "your query"                    # Auto-detect mode
    python exa_search.py "query" --mode code             # Force code search
    python exa_search.py "query" --category github       # Filter by category
    python exa_search.py "query" --days 7 --highlights   # Recent with highlights

Examples:
    python exa_search.py "Python asyncio gather examples"
    python exa_search.py "OpenAI GPT-5 announcement" --days 30
    python exa_search.py "Prisma ORM" --category github --highlights
    python exa_search.py "machine learning research" --category "research paper"
"""

import argparse
import sys
import os
import re
import concurrent.futures
from datetime import datetime, timedelta
from typing import Optional, List, Tuple

# Add script directory to path for local imports
script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, script_dir)

from exa_common import (
    make_mcp_request, print_error, print_info,
    direct_search, format_api_results, has_api_key, VALID_CATEGORIES
)

# =============================================================================
# Constants
# =============================================================================

WEB_TOOL = "web_search_exa"
CODE_TOOL = "get_code_context_exa"

DEFAULT_NUM_RESULTS = 8
DEFAULT_CODE_TOKENS = 5000
DEFAULT_TIMEOUT = 30
PARALLEL_TIMEOUT = 35

# Valid options for --type and --livecrawl
VALID_SEARCH_TYPES = {"auto", "fast", "deep"}
VALID_LIVECRAWL = {"never", "fallback", "preferred", "always"}

# =============================================================================
# Query Classification (Enhanced)
# =============================================================================

# Languages & frameworks (strong code signals)
LANG_KEYWORDS = {
    'python', 'javascript', 'typescript', 'react', 'vue', 'angular', 'svelte',
    'rust', 'go', 'golang', 'java', 'kotlin', 'swift', 'cpp', 'csharp', 'c#',
    'node', 'nodejs', 'deno', 'bun', 'django', 'flask', 'fastapi', 'express',
    'nextjs', 'nuxt', 'remix', 'prisma', 'drizzle', 'postgresql', 'mongodb',
    'redis', 'docker', 'kubernetes', 'aws', 'gcp', 'azure', 'terraform', 'git',
    'npm', 'pip', 'cargo', 'pnpm', 'yarn', 'vite', 'webpack', 'tailwind',
    'pytorch', 'tensorflow', 'pandas', 'numpy', 'scipy', 'sklearn'
}

# Code concepts and actions
CODE_KEYWORDS = {
    'function', 'method', 'class', 'interface', 'api', 'endpoint', 'rest',
    'graphql', 'websocket', 'library', 'package', 'module', 'import', 'export',
    'async', 'await', 'callback', 'promise', 'hook', 'component', 'props',
    'middleware', 'router', 'controller', 'model', 'schema', 'migration',
    'example', 'examples', 'tutorial', 'docs', 'documentation', 'sdk',
    'implement', 'syntax', 'usage', 'snippet', 'code', 'coding',
    'error', 'fix', 'debug', 'install', 'setup', 'configure', 'config'
}

# News/current events indicators
NEWS_KEYWORDS = {
    'news', 'latest', 'recent', 'announced', 'released', 'launching', 'launch',
    'update', 'updates', 'version', 'today', 'yesterday', 'this week',
    '2024', '2025', '2026', 'breaking', 'announcement', 'preview', 'beta',
    'rumor', 'leak', 'report', 'says', 'confirms', 'reveals'
}

# Research/comparison indicators
RESEARCH_KEYWORDS = {
    'vs', 'versus', 'comparison', 'compare', 'difference', 'differences',
    'between', 'better', 'best', 'worst', 'tradeoff', 'tradeoffs',
    'pros', 'cons', 'advantages', 'disadvantages', 'alternatives', 'alternative',
    'benchmark', 'performance', 'review', 'analysis', 'study', 'research'
}

# GitHub-specific signals
GITHUB_SIGNALS = {
    'github', 'repo', 'repository', 'repositories', 'starred', 'stars',
    'fork', 'forks', 'open source', 'opensource', 'oss', 'mit license',
    'npm package', 'pypi', 'crates.io', 'awesome list'
}

# Company/product signals
COMPANY_SIGNALS = {
    'company', 'startup', 'pricing', 'plans', 'enterprise', 'saas',
    'founded', 'ceo', 'funding', 'valuation', 'competitors', 'market'
}

# Academic/research paper signals
PAPER_SIGNALS = {
    'paper', 'papers', 'arxiv', 'research', 'study', 'journal', 'publication',
    'abstract', 'methodology', 'findings', 'hypothesis', 'experiment',
    'peer reviewed', 'citations', 'authors', 'phd', 'thesis'
}


def classify_query(query: str) -> Tuple[str, Optional[str]]:
    """
    Classify query to determine best search strategy and category.

    Returns:
        (mode, suggested_category)
        - mode: 'code', 'news', 'dual', 'web'
        - suggested_category: category to use if API key available
    """
    query_lower = query.lower()
    words = set(re.findall(r'\b\w+\b', query_lower))

    # Count keyword matches
    lang_score = len(words & LANG_KEYWORDS)
    code_score = len(words & CODE_KEYWORDS) + lang_score
    news_score = len(words & NEWS_KEYWORDS)
    research_score = len(words & RESEARCH_KEYWORDS)
    github_score = len(words & GITHUB_SIGNALS)
    company_score = len(words & COMPANY_SIGNALS)
    paper_score = len(words & PAPER_SIGNALS)

    # Check for phrase patterns
    if 'how to' in query_lower or 'how do' in query_lower:
        code_score += 2
    if 'what is' in query_lower and code_score >= 1:
        code_score += 1
    if 'best practices' in query_lower:
        code_score += 1
        research_score += 1

    # Determine suggested category
    suggested_category = None
    if github_score >= 2 or (github_score >= 1 and code_score >= 2):
        suggested_category = "github"
    elif paper_score >= 2:
        suggested_category = "research paper"
    elif company_score >= 2:
        suggested_category = "company"
    elif news_score >= 2 and code_score == 0:
        suggested_category = "news"

    # Determine mode
    # Strong code signal, no news/research -> code only
    if code_score >= 2 and news_score == 0 and research_score == 0:
        return ('code', suggested_category)

    # News terms without code -> news (web with livecrawl)
    if news_score >= 1 and code_score == 0:
        return ('news', suggested_category or 'news')

    # Mixed: code + news, or code + research -> dual
    if code_score >= 1 and (news_score >= 1 or research_score >= 1):
        return ('dual', suggested_category)

    # Some code terms -> code
    if code_score >= 1:
        return ('code', suggested_category)

    # Research without code -> web
    if research_score >= 1:
        return ('web', suggested_category)

    # Default: web search
    return ('web', suggested_category)


# =============================================================================
# Search Functions
# =============================================================================

def _web_search_mcp(
    query: str,
    num_results: int,
    search_type: str = 'auto',
    livecrawl: str = 'fallback'
) -> str:
    """Basic web search via MCP (free, no API key)."""
    arguments = {
        "query": query,
        "numResults": num_results,
        "type": search_type,
        "livecrawl": livecrawl,
        "contextMaxCharacters": 8000
    }
    return make_mcp_request(WEB_TOOL, arguments, timeout=DEFAULT_TIMEOUT)


def _code_search_mcp(query: str, tokens: int = DEFAULT_CODE_TOKENS) -> str:
    """Code search via MCP (free, no API key)."""
    arguments = {
        "query": query,
        "tokensNum": tokens
    }
    return make_mcp_request(CODE_TOOL, arguments, timeout=DEFAULT_TIMEOUT)


def _web_search_advanced(
    query: str,
    num_results: int,
    search_type: str = 'auto',
    category: Optional[str] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    use_highlights: bool = False,
    use_summary: bool = False,
    livecrawl: str = 'fallback'
) -> str:
    """Advanced web search via direct API (requires API key)."""
    response = direct_search(
        query=query,
        num_results=num_results,
        search_type=search_type,
        category=category,
        include_domains=include_domains,
        exclude_domains=exclude_domains,
        start_published_date=start_date,
        end_published_date=end_date,
        use_highlights=use_highlights,
        use_summary=use_summary,
        livecrawl=livecrawl
    )
    return format_api_results(response, query, result_type="search")


def _raw_url_search(
    query: str,
    num_results: int,
    search_type: str = 'auto',
    category: Optional[str] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    livecrawl: str = 'fallback'
) -> str:
    """
    Search and return only URLs, one per line.

    Uses direct API to get structured results, then extracts just the URLs.
    Useful for piping to other tools or quick reference gathering.
    """
    try:
        response = direct_search(
            query=query,
            num_results=num_results,
            search_type=search_type,
            category=category,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            start_published_date=start_date,
            end_published_date=end_date,
            livecrawl=livecrawl
        )

        results = response.get("results", [])
        if not results:
            return "# No results found"

        urls = [r.get("url", "") for r in results if r.get("url")]
        return '\n'.join(urls)

    except Exception as e:
        return f"[ERROR] {e}"


def _parallel_search(
    query: str,
    num_results: int,
    code_tokens: int,
    search_type: str = 'auto',
    livecrawl: str = 'fallback',
    category: Optional[str] = None,
    use_advanced: bool = False
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Run web and code search in parallel."""
    web_result = None
    code_result = None
    web_error = None
    code_error = None

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        if use_advanced and has_api_key():
            web_future = executor.submit(
                _web_search_advanced, query, num_results,
                search_type=search_type, category=category,
                use_highlights=True, livecrawl=livecrawl
            )
        else:
            web_future = executor.submit(
                _web_search_mcp, query, num_results,
                search_type=search_type, livecrawl=livecrawl
            )

        code_future = executor.submit(_code_search_mcp, query, code_tokens)

        try:
            web_result = web_future.result(timeout=PARALLEL_TIMEOUT)
        except Exception as e:
            web_error = str(e)

        try:
            code_result = code_future.result(timeout=PARALLEL_TIMEOUT)
        except Exception as e:
            code_error = str(e)

    return web_result, web_error, code_result, code_error


# =============================================================================
# Main Smart Search Function
# =============================================================================

def smart_search(
    query: str,
    mode: str = 'auto',
    num_results: int = DEFAULT_NUM_RESULTS,
    code_tokens: int = DEFAULT_CODE_TOKENS,
    # Search behavior options
    search_type: str = 'auto',
    livecrawl: str = 'fallback',
    # Advanced options
    category: Optional[str] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    use_highlights: bool = False,
    use_summary: bool = False,
    # Output format options
    raw_output: bool = False
) -> str:
    """
    Perform intelligent search using Exa AI.

    Auto-detects query type and routes to best search method.
    Uses advanced features when EXA_API_KEY is available.

    Args:
        query: Search query
        mode: 'auto', 'web', 'code', 'news', or 'dual'
        num_results: Number of web results
        code_tokens: Tokens for code search
        search_type: 'auto', 'fast', or 'deep' - controls search depth
        livecrawl: 'never', 'fallback', 'preferred', 'always' - fresh content
        category: Filter category (github, news, research paper, etc.)
        include_domains: Only these domains
        exclude_domains: Exclude these domains
        start_date: Content after this date (ISO 8601)
        end_date: Content before this date (ISO 8601)
        use_highlights: Include AI snippets
        use_summary: Include AI summary
        raw_output: Output only URLs (one per line)

    Returns:
        Formatted search results (or raw URLs if raw_output=True)
    """
    query = query.strip() if query else ""
    if not query:
        return "[ERROR] Empty query. Please provide a search term."

    # Determine mode and auto-suggest category
    if mode == 'auto':
        detected_mode, suggested_category = classify_query(query)
        mode_info = f"{detected_mode} (auto-detected)"

        # Use suggested category if none provided and we have API key
        if not category and suggested_category and has_api_key():
            category = suggested_category
    else:
        detected_mode = mode
        mode_info = mode

    # Check if advanced features requested
    needs_advanced = any([
        category, include_domains, exclude_domains,
        start_date, end_date, use_highlights, use_summary
    ])
    use_advanced = needs_advanced and has_api_key()

    # For raw output, we need to use the direct API to get structured results
    if raw_output and has_api_key():
        return _raw_url_search(
            query=query,
            num_results=num_results,
            search_type=search_type,
            category=category,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            start_date=start_date,
            end_date=end_date,
            livecrawl=livecrawl
        )
    elif raw_output:
        return "[ERROR] --raw mode requires EXA_API_KEY (needed for structured results)"

    output = []
    output.append("=== Exa Smart Search ===")
    output.append(f"Query: {query}")
    output.append(f"Mode: {mode_info}")
    if category:
        output.append(f"Category: {category}")
    if use_advanced:
        output.append("[Using advanced API features]")
    output.append("")

    try:
        if detected_mode == 'code':
            results = _code_search_mcp(query, code_tokens)
            output.append("--- Code/Documentation Results ---")
            output.append(results if results else "No results found.")

        elif detected_mode == 'news':
            # For news, prefer fresh content unless explicitly set otherwise
            news_livecrawl = livecrawl if livecrawl != 'fallback' else 'preferred'
            if use_advanced:
                results = _web_search_advanced(
                    query, num_results,
                    search_type=search_type,
                    category=category or 'news',
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                    start_date=start_date,
                    end_date=end_date,
                    use_highlights=use_highlights,
                    use_summary=use_summary,
                    livecrawl=news_livecrawl
                )
            else:
                results = _web_search_mcp(query, num_results, search_type, news_livecrawl)
            output.append("--- News/Recent Results ---")
            output.append(results if results else "No results found.")

        elif detected_mode == 'dual':
            web_res, web_err, code_res, code_err = _parallel_search(
                query, num_results, code_tokens,
                search_type=search_type, livecrawl=livecrawl,
                category=category, use_advanced=use_advanced
            )

            output.append("### Web Results ###")
            if web_res:
                output.append(web_res)
            elif web_err:
                output.append(f"[Web search failed: {web_err}]")
            else:
                output.append("No web results found.")
            output.append("")

            output.append("### Code/Documentation Results ###")
            if code_res:
                output.append(code_res)
            elif code_err:
                output.append(f"[Code search failed: {code_err}]")
            else:
                output.append("No code results found.")

        else:  # 'web' mode
            if use_advanced:
                results = _web_search_advanced(
                    query, num_results,
                    search_type=search_type,
                    category=category,
                    include_domains=include_domains,
                    exclude_domains=exclude_domains,
                    start_date=start_date,
                    end_date=end_date,
                    use_highlights=use_highlights,
                    use_summary=use_summary,
                    livecrawl=livecrawl
                )
            else:
                results = _web_search_mcp(query, num_results, search_type, livecrawl)
            output.append("--- Web Results ---")
            output.append(results if results else "No results found.")

    except Exception as e:
        output.append(f"[ERROR] Search failed: {e}")

    output.append("")
    return '\n'.join(output)


# =============================================================================
# CLI Interface
# =============================================================================

def parse_args():
    """Parse command line arguments."""
    categories_list = ", ".join(sorted(VALID_CATEGORIES))

    parser = argparse.ArgumentParser(
        description="Unified smart search - auto-detects query type and uses best strategy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Auto-Detection Modes:
  code  - Programming, APIs, libraries -> code documentation search
  news  - Recent events, releases -> web search with fresh content
  dual  - Technical + current -> parallel web + code search
  web   - General queries -> standard web search

Examples:
  %(prog)s "Python asyncio patterns"                    -> code
  %(prog)s "OpenAI GPT-5 announcement 2025"             -> news
  %(prog)s "FastAPI vs Flask performance comparison"    -> dual
  %(prog)s "climate change effects"                     -> web

With Advanced Features (requires EXA_API_KEY):
  %(prog)s "React hooks" --category github --highlights
  %(prog)s "AI news" --days 7 --category news
  %(prog)s "Python" --include-domains docs.python.org,realpython.com

Available Categories:
  {categories_list}
        """
    )

    parser.add_argument(
        "query",
        nargs='+',
        help="Search query (multiple words joined automatically - quotes optional)"
    )

    parser.add_argument(
        "--mode", "-m",
        choices=["auto", "web", "code", "news", "dual"],
        default="auto",
        help="Search mode (default: auto)"
    )

    parser.add_argument(
        "--num-results", "-n",
        type=int,
        default=DEFAULT_NUM_RESULTS,
        help=f"Number of web results (default: {DEFAULT_NUM_RESULTS})"
    )

    parser.add_argument(
        "--code-tokens", "-t",
        type=int,
        default=DEFAULT_CODE_TOKENS,
        help=f"Tokens for code search (default: {DEFAULT_CODE_TOKENS})"
    )

    parser.add_argument(
        "--type",
        choices=list(VALID_SEARCH_TYPES),
        default="auto",
        help="Search depth: auto, fast (quick), or deep (thorough)"
    )

    parser.add_argument(
        "--livecrawl",
        choices=list(VALID_LIVECRAWL),
        default="fallback",
        help="Fresh content: never, fallback, preferred, always"
    )

    # Advanced options
    advanced = parser.add_argument_group('Advanced Options (require EXA_API_KEY)')

    advanced.add_argument(
        "--category", "-c",
        choices=list(VALID_CATEGORIES),
        help="Filter by category (auto-suggested when possible)"
    )

    advanced.add_argument(
        "--include-domains",
        type=str,
        help="Comma-separated domains to include"
    )

    advanced.add_argument(
        "--exclude-domains",
        type=str,
        help="Comma-separated domains to exclude"
    )

    advanced.add_argument(
        "--days",
        type=int,
        help="Only content from last N days"
    )

    advanced.add_argument(
        "--start-date",
        type=str,
        help="Content after this date (YYYY-MM-DD)"
    )

    advanced.add_argument(
        "--end-date",
        type=str,
        help="Content before this date (YYYY-MM-DD)"
    )

    advanced.add_argument(
        "--highlights",
        action="store_true",
        help="Include AI-selected snippets"
    )

    advanced.add_argument(
        "--summary",
        action="store_true",
        help="Include AI-generated summary"
    )

    # Output format options
    output_group = parser.add_argument_group('Output Format')

    output_group.add_argument(
        "--raw",
        action="store_true",
        help="Output URLs only, one per line (for piping to other tools)"
    )

    return parser.parse_args()


def main():
    """Main entry point."""
    args = parse_args()

    # Join query words (supports both quoted and unquoted multi-word queries)
    query = ' '.join(args.query)

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
        start_dt = datetime.now() - timedelta(days=args.days)
        start_date = start_dt.strftime("%Y-%m-%dT00:00:00.000Z")

    try:
        results = smart_search(
            query=query,
            mode=args.mode,
            num_results=args.num_results,
            code_tokens=args.code_tokens,
            search_type=args.type,
            livecrawl=args.livecrawl,
            category=args.category,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            start_date=start_date,
            end_date=end_date,
            use_highlights=args.highlights,
            use_summary=args.summary,
            raw_output=args.raw
        )
        print(results)
        return 0

    except Exception as e:
        print_error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
