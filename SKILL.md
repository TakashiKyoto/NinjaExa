---
name: ninjaexa
description: Search the web using NinjaExa (Exa AI) for real-time information, current events, and technical documentation. Use this skill when you need up-to-date information beyond your knowledge cutoff, researching libraries/frameworks/APIs, finding recent news, or getting code examples. Triggers on queries about recent events, library docs, API references, or when user explicitly asks to search the web.
---

# NinjaExa - AI-Powered Web Search

Unified search tool using Exa AI's neural search. Smart auto-detection routes queries to the best search strategy.

## Quick Start

```bash
ninjaexa "your query"    # Smart auto-detect (handles 90% of use cases)
```

## Subcommands

| Command | Use Case | Example |
|---------|----------|---------|
| `ninjaexa "query"` | **Auto-detect** - routes intelligently | `ninjaexa "Python asyncio examples"` |
| `ninjaexa web "query"` | General web search | `ninjaexa web "AI news 2025"` |
| `ninjaexa code "query"` | Code docs, APIs, examples | `ninjaexa code "React useEffect"` |
| `ninjaexa news "query"` | Fresh/recent content | `ninjaexa news "OpenAI announcement"` |
| `ninjaexa dual "query"` | Parallel web + code | `ninjaexa dual "FastAPI vs Flask"` |
| `ninjaexa crawl "url"` | Extract URL content | `ninjaexa crawl "https://..."` |
| `ninjaexa similar "url"` | Find similar content | `ninjaexa similar "https://..."` |
| `ninjaexa deep "query"` | Deep research + synthesis | `ninjaexa deep "microservices tradeoffs"` |

## Common Options

| Option | Description | Example |
|--------|-------------|---------|
| `--num-results N` | Number of results (default: 8) | `--num-results 15` |
| `--code-tokens N` | Tokens for code search (default: 5000) | `--code-tokens 10000` |
| `--type` | Search depth: auto/fast/deep | `--type fast` |
| `--livecrawl` | Fresh content: never/fallback/preferred/always | `--livecrawl preferred` |

## Advanced Options (require EXA_API_KEY)

| Option | Description |
|--------|-------------|
| `--category` | Filter: `github`, `news`, `research paper`, `company`, `pdf`, `tweet` |
| `--include-domains` | Only search specific domains (comma-separated) |
| `--exclude-domains` | Exclude specific domains (comma-separated) |
| `--days N` | Only content from last N days |
| `--highlights` | AI-selected relevant snippets |
| `--summary` | AI-generated summary per result |

## Examples

```bash
# Auto-detect examples (no subcommand needed - recommended)
ninjaexa "Python asyncio gather examples"     # -> code mode
ninjaexa "OpenAI GPT-5 announcement 2025"     # -> news mode
ninjaexa "React vs Vue comparison"            # -> dual mode

# Explicit subcommands
ninjaexa web "climate change effects" --num-results 10
ninjaexa code "Prisma ORM relationships" --code-tokens 8000
ninjaexa news "AI news" --days 7

# Advanced (with API key)
ninjaexa "React hooks" --category github --highlights
ninjaexa web "machine learning" --category "research paper" --days 30

# URL tools (require API key)
ninjaexa crawl "https://react.dev/blog/2024/04/25/react-19"
ninjaexa similar "https://cursor.sh" --category company
ninjaexa deep "microservices vs monolith tradeoffs"
```

## Auto-Detection Logic

| Query Contains | Detected Mode |
|----------------|---------------|
| Language names, "example", "how to", API terms | `code` |
| "news", "latest", dates (2024/2025), "released" | `news` |
| Code terms + news/comparison terms | `dual` (parallel) |
| General queries | `web` |

## Premium Tools (require EXA_API_KEY)

| Tool | Purpose |
|------|---------|
| `ninjaexa crawl` | Extract content from URLs (bypasses Cloudflare, paywalls, JS sites) |
| `ninjaexa similar` | Find content similar to a URL (competitor analysis, alternatives) |
| `ninjaexa deep` | Deep research with AI query expansion and synthesis |
| `--category` filter | Restrict to github/news/research paper/company/pdf/tweet |
| `--highlights/--summary` | AI-enhanced result formatting |

## API Key Setup

Basic search works without an API key. Premium features require `EXA_API_KEY`:

```bash
# Linux/WSL - add to ~/.bashrc or ~/.bash/secrets.sh
export EXA_API_KEY="your-key-here"

# Windows - add to PowerShell profile or use setx
$env:EXA_API_KEY = "your-key-here"   # In $PROFILE
setx EXA_API_KEY "your-key-here"     # Or permanent env var
```

Auto-detected locations (cached 24h): `~/.bash/*.sh` (Linux), PowerShell profiles (Windows). Get key: https://exa.ai

## Why NinjaExa Over WebFetch

| Issue | WebFetch | NinjaExa |
|-------|----------|----------|
| Cloudflare sites | Blocked | Works (pre-cached) |
| Paywalls | Blocked | Often works |
| JS-heavy SPAs | Empty/broken | Pre-rendered content |
| Rate limiting | Gets blocked | No limit |

## Technical Details

- **Endpoint**: `https://mcp.exa.ai/mcp` (Exa's hosted MCP server)
- **Protocol**: JSON-RPC 2.0 over HTTP with SSE responses
- **Timeout**: 30-45 seconds depending on tool
- **Dependencies**: Python 3.x (stdlib only)

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Timeout | Use `--type fast` for quicker results |
| No results | Add language/framework name, try more specific terms |
| Premium tool error | Set `EXA_API_KEY` environment variable |
| URL not extracted | May not be in Exa's cache; try recently popular pages |

## Testing

```bash
python test/run_test_ninjaexa.py --fast   # Quick validation (~2s)
python test/run_test_ninjaexa.py          # Full suite (~20s)
```
