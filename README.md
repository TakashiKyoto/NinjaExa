# NinjaExa - AI-Powered Web Search for Claude Code

Unified search tool using Exa AI's neural search technology. Smart auto-detection routes queries to the best search strategy.

## Quick Start

```bash
ninjaexa "your query"    # Smart auto-detect - handles 90% of use cases
```

## Features

- **Smart Auto-Detect**: Automatically routes to code, news, web, or dual mode
- **Unified Wrapper**: One command (`ninjaexa`) for all search types
- **Parallel Search**: Dual mode runs web + code simultaneously
- **URL Extraction**: Bypasses Cloudflare, paywalls, JS-heavy sites
- **Zero Config**: Works without API key (premium features optional)
- **Cross-Platform**: Works on WSL, Linux, and Windows

## Why NinjaExa Over WebFetch

| Aspect | WebFetch | NinjaExa |
|--------|----------|----------|
| Returns | Often blocked | **Content inline** |
| Cloudflare sites | Fails | **Works (pre-cached)** |
| JS-heavy SPAs | Empty/broken | **Pre-rendered content** |
| Rate limiting | Gets blocked | **Smart limits (abuse protection)** |

## Installation

### Option 1: Git Clone (Recommended)

```bash
git clone https://github.com/TakashiKyoto/NinjaExa.git ~/.ninjaexa
ln -sf ~/.ninjaexa/scripts/ninjaexa ~/bin/ninjaexa
```

### Option 2: As Claude Code Skill

```bash
mkdir -p ~/.claude/skills/ninjaexa
cp -r ./* ~/.claude/skills/ninjaexa/

# Optional: Create symlink for CLI access
mkdir -p ~/bin
ln -sf ~/.claude/skills/ninjaexa/scripts/ninjaexa ~/bin/ninjaexa
```

## Usage

### Subcommands

```bash
ninjaexa "query"              # Smart auto-detect (RECOMMENDED)
ninjaexa web "query"          # Force web search
ninjaexa code "query"         # Force code/docs search
ninjaexa news "query"         # Force news (fresh content)
ninjaexa dual "query"         # Parallel web + code
ninjaexa crawl "url"          # Extract URL content
ninjaexa similar "url"        # Find similar content
ninjaexa deep "query"         # Deep research + synthesis
```

### Examples

```bash
# Auto-detect (no subcommand needed)
ninjaexa "Python asyncio examples"           # -> code mode
ninjaexa "AI news December 2025"             # -> news mode
ninjaexa "FastAPI vs Flask 2025"             # -> dual mode

# With options
ninjaexa "React hooks" --highlights --category github
ninjaexa web "AI announcements" --days 7
ninjaexa code "Prisma ORM" --code-tokens 10000

# Premium tools (require API key)
ninjaexa crawl "https://react.dev/blog/2024/04/25/react-19"
ninjaexa similar "https://cursor.sh" --category company
ninjaexa deep "microservices vs monolith tradeoffs"
```

## Options Reference

| Option | Description |
|--------|-------------|
| `--num-results N` | Number of results (default: 8) |
| `--code-tokens N` | Tokens for code search (default: 5000) |
| `--type` | Search depth: auto/fast/deep |
| `--livecrawl` | Fresh content: never/fallback/preferred/always |
| `--category` | Filter: github, news, research paper, company, pdf, tweet |
| `--include-domains` | Only search specific domains |
| `--exclude-domains` | Exclude specific domains |
| `--days N` | Only content from last N days |
| `--highlights` | AI-selected relevant snippets |
| `--summary` | AI-generated summary per result |

## API Key Setup

Basic search works without an API key. Premium features require `EXA_API_KEY`:

```bash
# Linux/WSL - add to ~/.bashrc or ~/.bash/*.sh
export EXA_API_KEY="your-key-here"

# Windows - add to PowerShell profile ($PROFILE) or use setx
$env:EXA_API_KEY = "your-key-here"   # In profile
setx EXA_API_KEY "your-key-here"     # Or permanent env var
```

Auto-detected locations (cached 24h): `~/.bash/*.sh` (Linux), PowerShell profiles (Windows).

Get your key: https://exa.ai (free tier available)

## Rate Limiting (Abuse Protection)

NinjaExa includes smart rate limiting to prevent runaway scripts or AI agents from burning through API credits. Designed to be **invisible during normal use** but kicks in hard when abused.

### How It Works

| Usage Level | Behavior |
|-------------|----------|
| **Normal** (< 15/min) | No delay, no warnings |
| **Busy** (15-22/min) | Warning message, no delay |
| **Heavy** (22-30/min) | Warning + small delay |
| **Abuse** (> 30/min) | **Exponential backoff** (3s → 6s → 12s → ... → 10min max) |
| **Hard cap** (200/hr, 1000/day) | **Blocked** until reset |

### Exponential Backoff

When abuse is detected:
- First violation: 3 second delay
- Second violation: 6 seconds
- Third: 12 seconds
- Continues doubling up to 10 minute max

Penalties **decay automatically** after 10 minutes of normal behavior.

### Default Limits

| Window | Limit |
|--------|-------|
| Per minute | 15 |
| Per 10 minutes | 60 |
| Per hour | 200 |
| Per day | 1000 |

### Customization (Environment Variables)

```bash
# Override limits (example: more permissive for power users)
export NINJAEXA_RATE_PER_MIN=30
export NINJAEXA_RATE_PER_10MIN=120
export NINJAEXA_RATE_PER_HOUR=500
export NINJAEXA_RATE_PER_DAY=2000

# Disable entirely (testing only - NOT recommended)
export NINJAEXA_NO_RATE_LIMIT=1
```

### Tuning the Backoff Behavior

Edit `scripts/exa_rate_limiter.py` top section to adjust:

```python
# When delays kick in (multipliers of the per-minute limit)
BURST_WARNING_THRESHOLD = 1.5  # 1.5x limit = warning only
BURST_DELAY_THRESHOLD = 2.0    # 2x limit = delays start

# Exponential backoff settings
BASE_PENALTY_SECONDS = 3.0     # First violation delay
MAX_PENALTY_SECONDS = 600.0    # Cap at 10 minutes
PENALTY_MULTIPLIER = 2.0       # Doubles each violation
PENALTY_DECAY_MINUTES = 10     # Good behavior recovery time
```

**Example tuning for stricter limits:**
```python
BURST_WARNING_THRESHOLD = 1.2  # Warn earlier
BURST_DELAY_THRESHOLD = 1.5    # Delay sooner
BASE_PENALTY_SECONDS = 5.0     # Harsher starting penalty
```

**Example for more lenient limits:**
```python
BURST_WARNING_THRESHOLD = 2.0  # Warn later
BURST_DELAY_THRESHOLD = 3.0    # Delay much later
BASE_PENALTY_SECONDS = 1.0     # Gentler starting penalty
PENALTY_DECAY_MINUTES = 5      # Recover faster
```

### Check Status

```bash
python scripts/exa_rate_limiter.py --status   # View current usage
python scripts/exa_rate_limiter.py --reset    # Reset state (after fixing issues)
```

### Why This Exists

- Normal humans/AI: Unaffected (15/min is generous)
- Runaway scripts: Automatically throttled then blocked
- API credits: Protected

## Testing

Automated test suite for quick validation after changes:

```bash
# Fast static tests only (~2 seconds) - syntax, help, classification
python test/run_test_ninjaexa.py --fast

# Full test suite (~20 seconds) - includes network tests
python test/run_test_ninjaexa.py

# Verbose output
python test/run_test_ninjaexa.py --verbose
```

| Test Category | Count | What it tests |
|---------------|-------|---------------|
| Static | 22 | Syntax, help output, query classification, options |
| Network | 6 | web/code/news/dual/auto-detect searches |
| Premium | 3 | similar/crawl/deep (requires API key) |

## File Structure

```
ninjaexa/
├── SKILL.md                  # Claude skill definition
├── README.md                 # This file
├── LICENSE                   # MIT License
├── scripts/
│   ├── ninjaexa              # Unified wrapper (USE THIS)
│   ├── exa_common.py         # Shared utilities
│   ├── exa_search.py         # Smart search engine
│   ├── exa_similar.py        # Find similar content
│   ├── exa_deepsearch.py     # Deep research
│   └── exa_crawling.py       # URL extraction
└── test/
    └── run_test_ninjaexa.py  # Automated test suite
```

## Technical Details

- **Endpoint**: `https://mcp.exa.ai/mcp` (Exa's hosted MCP server)
- **Protocol**: JSON-RPC 2.0 over HTTP with SSE responses
- **Timeout**: 30-45 seconds depending on tool
- **Dependencies**: Python 3.x (stdlib only - no pip install required)

## Requirements

- Python 3.8 or higher
- No external dependencies (uses Python standard library only)

## License

MIT License - see [LICENSE](LICENSE) file for details.
