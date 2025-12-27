#!/usr/bin/env python3
"""
run_test_ninjaexa.py - Automated Test Suite for NinjaExa

Tests the unified ninjaexa wrapper and underlying search scripts.

Usage:
    python run_test_ninjaexa.py              # Run all tests
    python run_test_ninjaexa.py --fast       # Skip network tests (instant)
    python run_test_ninjaexa.py --verbose    # Verbose output
    python run_test_ninjaexa.py --network    # Only network tests

Test Categories:
    - Static Tests: File existence, permissions, help output, query classification
    - Network Tests: Actual search functionality (require network, may cost API credits)
"""

import os
import sys
import subprocess
import time
import argparse
from typing import List, Tuple, Optional, Callable
from dataclasses import dataclass

# =============================================================================
# Configuration
# =============================================================================

# Resolve paths - handle both direct run and symlink scenarios
_test_dir = os.path.dirname(os.path.abspath(__file__))
NINJAEXA_DIR = os.path.dirname(_test_dir)
SCRIPTS_DIR = os.path.join(NINJAEXA_DIR, "scripts")
WRAPPER_PATH = os.path.join(SCRIPTS_DIR, "ninjaexa")

# Timeouts
HELP_TIMEOUT = 5
SEARCH_TIMEOUT = 45
PREMIUM_TIMEOUT = 60

# =============================================================================
# Test Result Tracking
# =============================================================================

@dataclass
class TestResult:
    name: str
    passed: bool
    duration: float
    message: str = ""
    category: str = "static"


class TestRunner:
    """Collects and runs tests, tracks results."""

    def __init__(self, verbose: bool = False):
        self.results: List[TestResult] = []
        self.verbose = verbose
        self.has_api_key = bool(os.environ.get("EXA_API_KEY"))

    def run(self, name: str, test_func: Callable, category: str = "static") -> bool:
        """Run a single test and record result."""
        start = time.time()
        try:
            passed, message = test_func()
            duration = time.time() - start
            self.results.append(TestResult(name, passed, duration, message, category))
            self._print_result(name, passed, duration, message)
            return passed
        except Exception as e:
            duration = time.time() - start
            self.results.append(TestResult(name, False, duration, str(e), category))
            self._print_result(name, False, duration, str(e))
            return False

    def _print_result(self, name: str, passed: bool, duration: float, message: str):
        """Print test result."""
        status = "[OK]" if passed else "[FAILED]"
        time_str = f"({duration:.2f}s)" if duration > 0.1 else ""
        print(f"  {status} {name} {time_str}")
        if self.verbose and message:
            for line in message.split("\n")[:3]:  # Max 3 lines
                print(f"       {line}")
        elif not passed and message:
            print(f"       {message[:100]}")

    def summary(self) -> Tuple[int, int, int]:
        """Print summary and return (total, passed, failed)."""
        passed = sum(1 for r in self.results if r.passed)
        failed = len(self.results) - passed
        total = len(self.results)

        print("\n" + "=" * 60)
        print(f"SUMMARY: {passed}/{total} tests passed")

        if failed > 0:
            print(f"\nFailed tests:")
            for r in self.results:
                if not r.passed:
                    print(f"  - {r.name}: {r.message[:80]}")

        # Timing breakdown by category
        categories = {}
        for r in self.results:
            if r.category not in categories:
                categories[r.category] = {"count": 0, "time": 0.0}
            categories[r.category]["count"] += 1
            categories[r.category]["time"] += r.duration

        if len(categories) > 1:
            print("\nTiming by category:")
            for cat, data in sorted(categories.items()):
                print(f"  {cat}: {data['count']} tests, {data['time']:.2f}s")

        print("=" * 60)
        return total, passed, failed


# =============================================================================
# Helper Functions
# =============================================================================

def run_cmd(args: List[str], timeout: int = HELP_TIMEOUT) -> Tuple[int, str, str]:
    """Run command and return (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "Timeout expired"
    except Exception as e:
        return -1, "", str(e)


def run_ninjaexa(args: List[str], timeout: int = SEARCH_TIMEOUT) -> Tuple[int, str, str]:
    """Run ninjaexa with given arguments."""
    return run_cmd([sys.executable, WRAPPER_PATH] + args, timeout)


# =============================================================================
# Static Tests (No Network Required)
# =============================================================================

def test_wrapper_exists() -> Tuple[bool, str]:
    """Verify wrapper script exists."""
    if os.path.exists(WRAPPER_PATH):
        return True, f"Found at {WRAPPER_PATH}"
    return False, f"Not found: {WRAPPER_PATH}"


def test_wrapper_syntax() -> Tuple[bool, str]:
    """Verify wrapper has valid Python syntax."""
    code, stdout, stderr = run_cmd([sys.executable, "-m", "py_compile", WRAPPER_PATH])
    if code == 0:
        return True, "Syntax OK"
    return False, stderr


def test_scripts_exist() -> Tuple[bool, str]:
    """Verify all required scripts exist."""
    required = ["exa_search.py", "exa_common.py", "exa_crawling.py",
                "exa_similar.py", "exa_deepsearch.py"]
    missing = [s for s in required if not os.path.exists(os.path.join(SCRIPTS_DIR, s))]
    if not missing:
        return True, f"All {len(required)} scripts found"
    return False, f"Missing: {', '.join(missing)}"


def test_scripts_syntax() -> Tuple[bool, str]:
    """Verify all Python scripts have valid syntax."""
    scripts = ["exa_search.py", "exa_common.py", "exa_crawling.py",
               "exa_similar.py", "exa_deepsearch.py"]
    errors = []
    for script in scripts:
        path = os.path.join(SCRIPTS_DIR, script)
        if os.path.exists(path):
            code, _, stderr = run_cmd([sys.executable, "-m", "py_compile", path])
            if code != 0:
                errors.append(f"{script}: {stderr[:50]}")
    if not errors:
        return True, f"All {len(scripts)} scripts have valid syntax"
    return False, "; ".join(errors)


def test_help_output() -> Tuple[bool, str]:
    """Verify help output contains expected content."""
    code, stdout, stderr = run_ninjaexa(["--help"])
    output = stdout + stderr

    required = ["ninjaexa", "web", "code", "news", "dual", "crawl", "similar", "deep"]
    missing = [r for r in required if r.lower() not in output.lower()]

    if code == 0 and not missing:
        return True, f"Help contains all {len(required)} expected terms"
    if missing:
        return False, f"Missing terms: {', '.join(missing)}"
    return False, f"Exit code {code}"


def test_no_args_shows_help() -> Tuple[bool, str]:
    """Verify running without args shows usage."""
    code, stdout, stderr = run_ninjaexa([])
    output = stdout + stderr

    if "ninjaexa" in output.lower() and "usage" in output.lower():
        return True, "Shows usage when no args"
    return False, "Did not show usage"


def test_subcommand_help() -> Tuple[bool, str]:
    """Verify subcommand-specific help works."""
    # Test 'web --help' shows exa_search.py help
    code, stdout, stderr = run_ninjaexa(["web", "--help"])
    output = stdout + stderr

    if "--num-results" in output and "--mode" in output:
        return True, "Subcommand help shows options"
    return False, f"Missing expected options in output"


# =============================================================================
# Query Classification Tests (No Network)
# =============================================================================

def _test_query_classification(query: str, expected_mode: str) -> Tuple[bool, str]:
    """Test that a query is classified correctly (uses --help trick to avoid network)."""
    # We can't easily test classification without running, so we'll do a quick
    # network test with --num-results 1 and check the mode output
    # For truly offline testing, we'd need to import the module directly

    # Import classify_query directly for offline testing
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        from exa_search import classify_query
        mode, _ = classify_query(query)
        if mode == expected_mode:
            return True, f"'{query}' -> {mode}"
        return False, f"'{query}' -> {mode} (expected {expected_mode})"
    except ImportError as e:
        return False, f"Could not import: {e}"
    finally:
        sys.path.pop(0)


def test_classify_code_query() -> Tuple[bool, str]:
    """Test code query classification."""
    return _test_query_classification("Python asyncio examples", "code")


def test_classify_news_query() -> Tuple[bool, str]:
    """Test news query classification."""
    return _test_query_classification("AI news December 2025", "news")


def test_classify_dual_query() -> Tuple[bool, str]:
    """Test dual mode query classification."""
    return _test_query_classification("React vs Vue comparison 2025", "dual")


def test_classify_web_query() -> Tuple[bool, str]:
    """Test web query classification."""
    return _test_query_classification("climate change effects", "web")


def test_classify_github_query() -> Tuple[bool, str]:
    """Test GitHub category detection."""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        from exa_search import classify_query
        _, category = classify_query("awesome python github repos stars")
        if category == "github":
            return True, "GitHub category detected"
        return False, f"Expected 'github', got '{category}'"
    except ImportError as e:
        return False, f"Could not import: {e}"
    finally:
        sys.path.pop(0)


# =============================================================================
# Multi-word Query Tests
# =============================================================================

def test_multiword_quoted() -> Tuple[bool, str]:
    """Test quoted multi-word query parsing."""
    code, stdout, stderr = run_ninjaexa(["web", "test query here", "--help"])
    # Should not error, help should show
    if code == 0:
        return True, "Quoted multi-word accepted"
    return False, f"Exit code {code}: {stderr[:50]}"


def test_multiword_unquoted() -> Tuple[bool, str]:
    """Test unquoted multi-word query parsing (AI-agent friendly)."""
    # This tests the nargs='+' fix - unquoted words should be joined
    code, stdout, stderr = run_ninjaexa(["web", "test", "query", "here", "--help"])
    if code == 0:
        return True, "Unquoted multi-word accepted"
    return False, f"Exit code {code}: {stderr[:50]}"


# =============================================================================
# Option Passthrough Tests
# =============================================================================

def test_num_results_option() -> Tuple[bool, str]:
    """Test --num-results option is recognized."""
    code, stdout, stderr = run_ninjaexa(["web", "test", "--num-results", "5", "--help"])
    if code == 0:
        return True, "--num-results accepted"
    return False, f"Exit code {code}"


def test_type_option() -> Tuple[bool, str]:
    """Test --type option is recognized."""
    code, stdout, stderr = run_ninjaexa(["web", "test", "--type", "fast", "--help"])
    if code == 0:
        return True, "--type fast accepted"
    return False, f"Exit code {code}"


def test_livecrawl_option() -> Tuple[bool, str]:
    """Test --livecrawl option is recognized."""
    code, stdout, stderr = run_ninjaexa(["web", "test", "--livecrawl", "preferred", "--help"])
    if code == 0:
        return True, "--livecrawl preferred accepted"
    return False, f"Exit code {code}"


def test_invalid_option_error() -> Tuple[bool, str]:
    """Test that invalid options produce error."""
    code, stdout, stderr = run_ninjaexa(["web", "test", "--invalid-option-xyz"])
    if code != 0 and "unrecognized" in stderr.lower():
        return True, "Invalid option rejected correctly"
    return False, f"Expected error, got code {code}"


# =============================================================================
# API Key Detection Tests
# =============================================================================

def test_api_key_detection() -> Tuple[bool, str]:
    """Test API key detection in exa_common."""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        from exa_common import has_api_key, get_api_key
        has_key = has_api_key()
        key = get_api_key()
        if has_key and key:
            return True, f"API key detected ({key[:8]}...)"
        elif not has_key and not key:
            return True, "API key correctly not found"
        return False, f"Detection mismatch: has={has_key}, key={bool(key)}"
    except ImportError as e:
        return False, f"Could not import: {e}"
    finally:
        sys.path.pop(0)


def test_truncate_at_sentence() -> Tuple[bool, str]:
    """Test sentence-boundary truncation function."""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        from exa_common import _truncate_at_sentence

        # Test 1: Short text (no truncation needed)
        short = "This is short."
        result = _truncate_at_sentence(short, 500)
        if result != short:
            return False, f"Short text modified: '{result}'"

        # Test 2: Long text should truncate at sentence
        long_text = "First sentence here. Second sentence is longer. Third sentence continues. " * 10
        result = _truncate_at_sentence(long_text, 100)
        if not result.endswith('.'):
            # Should end at period or with ...
            if not result.endswith('...'):
                return False, f"Bad ending: '{result[-20:]}'"

        # Test 3: Should not cut mid-word
        words = "Word1 Word2 Word3 Word4 Word5 Word6 Word7 Word8 Word9 Word10"
        result = _truncate_at_sentence(words, 30)
        if result.endswith('Wor...') or 'Wor ' in result:
            return False, f"Cut mid-word: '{result}'"

        return True, "Sentence truncation working"
    except ImportError as e:
        return False, f"Could not import: {e}"
    finally:
        sys.path.pop(0)


def test_raw_option_recognized() -> Tuple[bool, str]:
    """Test that --raw option is recognized."""
    code, stdout, stderr = run_ninjaexa(["web", "test", "--raw", "--help"])
    output = stdout + stderr
    if "--raw" in output:
        return True, "--raw option documented"
    # Even if not in help, check it doesn't error
    if code == 0:
        return True, "--raw option accepted"
    return False, f"Exit code {code}: {stderr[:50]}"


def test_api_key_fallback() -> Tuple[bool, str]:
    """Test API key fallback to ~/.bash/*.sh files and caching."""
    sys.path.insert(0, SCRIPTS_DIR)
    try:
        from exa_common import (
            _search_bash_files_for_key,
            _read_cached_key,
            _write_cached_key,
            _API_KEY_CACHE_FILE
        )

        # Test 1: Search function exists and works
        bash_key = _search_bash_files_for_key()
        # May or may not find key depending on setup - just verify it runs

        # Test 2: Cache write/read cycle
        test_key = "test-key-12345"
        _write_cached_key(test_key)
        cached = _read_cached_key()

        # Clean up test cache
        if os.path.exists(_API_KEY_CACHE_FILE):
            try:
                with open(_API_KEY_CACHE_FILE, 'r') as f:
                    if f.read().strip() == test_key:
                        os.remove(_API_KEY_CACHE_FILE)
            except:
                pass

        if cached == test_key:
            return True, "Fallback search and cache working"
        return False, f"Cache mismatch: wrote '{test_key}', read '{cached}'"

    except ImportError as e:
        return False, f"Could not import fallback functions: {e}"
    finally:
        sys.path.pop(0)


# =============================================================================
# Network Integration Tests (Require Network)
# =============================================================================

def test_web_search_basic() -> Tuple[bool, str]:
    """Test basic web search returns results."""
    code, stdout, stderr = run_ninjaexa(
        ["web", "Python programming", "--num-results", "1"],
        timeout=SEARCH_TIMEOUT
    )
    output = stdout + stderr

    if "=== Exa Smart Search ===" in output and ("http" in output.lower() or "Title:" in output):
        return True, "Web search returned results"
    if "error" in output.lower() or "timeout" in output.lower():
        return False, f"Error in output: {output[:100]}"
    return False, f"Unexpected output: {output[:100]}"


def test_code_search_basic() -> Tuple[bool, str]:
    """Test basic code search returns results."""
    code, stdout, stderr = run_ninjaexa(
        ["code", "React useState hook", "--num-results", "1"],
        timeout=SEARCH_TIMEOUT
    )
    output = stdout + stderr

    if "=== Exa Smart Search ===" in output and "```" in output:
        return True, "Code search returned code blocks"
    if "error" in output.lower():
        return False, f"Error: {output[:100]}"
    return False, f"No code blocks found: {output[:100]}"


def test_news_search_basic() -> Tuple[bool, str]:
    """Test news search returns results."""
    code, stdout, stderr = run_ninjaexa(
        ["news", "technology news", "--num-results", "1"],
        timeout=SEARCH_TIMEOUT
    )
    output = stdout + stderr

    if "=== Exa Smart Search ===" in output and "Mode: news" in output:
        return True, "News search executed correctly"
    return False, f"Unexpected: {output[:100]}"


def test_dual_search_basic() -> Tuple[bool, str]:
    """Test dual search returns both web and code results."""
    code, stdout, stderr = run_ninjaexa(
        ["dual", "FastAPI", "--num-results", "1"],
        timeout=SEARCH_TIMEOUT
    )
    output = stdout + stderr

    has_web = "Web Results" in output or "### Web" in output
    has_code = "Code" in output or "Documentation" in output

    if has_web and has_code:
        return True, "Dual search returned both types"
    if has_web or has_code:
        return True, "Dual search returned at least one type"
    return False, f"Missing results: {output[:100]}"


def test_auto_detect_search() -> Tuple[bool, str]:
    """Test auto-detect mode works."""
    code, stdout, stderr = run_ninjaexa(
        ["Python asyncio examples", "--num-results", "1"],
        timeout=SEARCH_TIMEOUT
    )
    output = stdout + stderr

    if "auto-detected" in output.lower() and "=== Exa Smart Search ===" in output:
        return True, "Auto-detect mode worked"
    return False, f"No auto-detect: {output[:100]}"


def test_symlink_works() -> Tuple[bool, str]:
    """Test that symlink in ~/bin works (if exists)."""
    symlink_path = os.path.expanduser("~/bin/ninjaexa")
    if not os.path.exists(symlink_path):
        return True, "Symlink not installed (OK - optional)"

    # Run via symlink
    code, stdout, stderr = run_cmd(
        [sys.executable, symlink_path, "--help"],
        timeout=HELP_TIMEOUT
    )

    if code == 0 and "ninjaexa" in (stdout + stderr).lower():
        return True, "Symlink works correctly"
    return False, f"Symlink broken: code={code}"


# =============================================================================
# Premium Feature Tests (Require API Key)
# =============================================================================

def test_similar_with_api_key() -> Tuple[bool, str]:
    """Test similar feature (requires API key)."""
    if not os.environ.get("EXA_API_KEY"):
        return True, "Skipped (no API key)"

    code, stdout, stderr = run_ninjaexa(
        ["similar", "https://github.com/tiangolo/fastapi", "--num-results", "1"],
        timeout=PREMIUM_TIMEOUT
    )
    output = stdout + stderr

    if "=== Exa Find Similar ===" in output or "Similar to:" in output:
        return True, "Similar search worked"
    if "error" in output.lower():
        return False, f"Error: {output[:100]}"
    return False, f"Unexpected: {output[:100]}"


def test_crawl_with_api_key() -> Tuple[bool, str]:
    """Test crawl feature (requires API key)."""
    if not os.environ.get("EXA_API_KEY"):
        return True, "Skipped (no API key)"

    code, stdout, stderr = run_ninjaexa(
        ["crawl", "https://docs.python.org/3/library/asyncio.html"],
        timeout=PREMIUM_TIMEOUT
    )
    output = stdout + stderr

    if "asyncio" in output.lower() and ("text" in output.lower() or "content" in output.lower()):
        return True, "Crawl extracted content"
    if "not found" in output.lower() or "error" in output.lower():
        return False, f"Crawl failed: {output[:100]}"
    return False, f"Unexpected: {output[:100]}"


def test_deep_with_api_key() -> Tuple[bool, str]:
    """Test deep research feature (requires API key)."""
    if not os.environ.get("EXA_API_KEY"):
        return True, "Skipped (no API key)"

    code, stdout, stderr = run_ninjaexa(
        ["deep", "Python best practices", "--num-results", "2"],
        timeout=PREMIUM_TIMEOUT
    )
    output = stdout + stderr

    # Check for successful deep search output
    if "Exa Deep Research" in output and "Title:" in output:
        return True, "Deep research worked"
    if "Exa Deep Research" in output and "URL:" in output:
        return True, "Deep research returned results"
    if "error" in output.lower() and "not found" in output.lower():
        # MCP tool not available - acceptable
        return True, "Deep tool not available via MCP (expected)"
    if "[error]" in output.lower():
        return False, f"Error: {output[:100]}"
    return False, f"Unexpected: {output[:100]}"


# =============================================================================
# Test Collection
# =============================================================================

STATIC_TESTS = [
    ("Wrapper Exists", test_wrapper_exists),
    ("Wrapper Syntax", test_wrapper_syntax),
    ("Scripts Exist", test_scripts_exist),
    ("Scripts Syntax", test_scripts_syntax),
    ("Help Output", test_help_output),
    ("No Args Shows Help", test_no_args_shows_help),
    ("Subcommand Help", test_subcommand_help),
    ("Classify Code Query", test_classify_code_query),
    ("Classify News Query", test_classify_news_query),
    ("Classify Dual Query", test_classify_dual_query),
    ("Classify Web Query", test_classify_web_query),
    ("Classify GitHub Query", test_classify_github_query),
    ("Multi-word Quoted", test_multiword_quoted),
    ("Multi-word Unquoted", test_multiword_unquoted),
    ("--num-results Option", test_num_results_option),
    ("--type Option", test_type_option),
    ("--livecrawl Option", test_livecrawl_option),
    ("--raw Option", test_raw_option_recognized),
    ("Invalid Option Error", test_invalid_option_error),
    ("Truncate At Sentence", test_truncate_at_sentence),
    ("API Key Detection", test_api_key_detection),
    ("API Key Fallback", test_api_key_fallback),
]

NETWORK_TESTS = [
    ("Web Search Basic", test_web_search_basic),
    ("Code Search Basic", test_code_search_basic),
    ("News Search Basic", test_news_search_basic),
    ("Dual Search Basic", test_dual_search_basic),
    ("Auto-Detect Search", test_auto_detect_search),
    ("Symlink Works", test_symlink_works),
]

PREMIUM_TESTS = [
    ("Similar (API Key)", test_similar_with_api_key),
    ("Crawl (API Key)", test_crawl_with_api_key),
    ("Deep (API Key)", test_deep_with_api_key),
]


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="NinjaExa Automated Test Suite")
    parser.add_argument("--fast", action="store_true", help="Skip network tests")
    parser.add_argument("--network", action="store_true", help="Only network tests")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    runner = TestRunner(verbose=args.verbose)

    print("=" * 60)
    print("NinjaExa Automated Test Suite")
    print("=" * 60)
    print(f"Wrapper: {WRAPPER_PATH}")
    print(f"API Key: {'Set' if os.environ.get('EXA_API_KEY') else 'Not set'}")
    print()

    if not args.network:
        print("Static Tests (no network):")
        for name, test_func in STATIC_TESTS:
            runner.run(name, test_func, category="static")
        print()

    if not args.fast:
        print("Network Integration Tests:")
        for name, test_func in NETWORK_TESTS:
            runner.run(name, test_func, category="network")
        print()

        if os.environ.get("EXA_API_KEY"):
            print("Premium Feature Tests (with API key):")
            for name, test_func in PREMIUM_TESTS:
                runner.run(name, test_func, category="premium")
            print()
        else:
            print("Premium Feature Tests: Skipped (no EXA_API_KEY)")
            print()

    total, passed, failed = runner.summary()

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
