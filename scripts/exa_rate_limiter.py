#!/usr/bin/env python3
"""
exa_rate_limiter.py - Smart Rate Limiter with Exponential Backoff

Prevents runaway AI agents or scripts from burning through API credits.
Designed to be invisible during normal use but kicks in hard when abused.

Key Features:
- Token bucket with sliding window (allows bursts, enforces average)
- Exponential backoff on violations (5s -> 10s -> 20s -> ... -> 10min max)
- Automatic recovery (penalties decay over time)
- Hard caps per hour/day (absolute limits)
- Persistent state (survives script restarts)

The 2,600 searches in 10 minutes incident = 4.3 searches/second
Normal human use = 1-2 searches/minute
Normal AI agent = 5-10 searches/task

Thresholds are generous for normal use, strict for abuse.
"""

import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Tuple, Optional, List
from pathlib import Path

# =============================================================================
# Configuration (can be overridden via environment variables)
# =============================================================================

# Rate limits (searches per time window)
RATE_LIMIT_PER_MINUTE = int(os.environ.get("NINJAEXA_RATE_PER_MIN", "15"))
RATE_LIMIT_PER_10_MIN = int(os.environ.get("NINJAEXA_RATE_PER_10MIN", "60"))
RATE_LIMIT_PER_HOUR = int(os.environ.get("NINJAEXA_RATE_PER_HOUR", "200"))
RATE_LIMIT_PER_DAY = int(os.environ.get("NINJAEXA_RATE_PER_DAY", "1000"))

# Exponential backoff settings
BASE_PENALTY_SECONDS = 3.0  # Starting penalty
MAX_PENALTY_SECONDS = 600.0  # 10 minutes max
PENALTY_MULTIPLIER = 2.0  # Doubles each violation
PENALTY_DECAY_MINUTES = 10  # Penalty halves every 10 min of good behavior

# Burst allowance (above limit but not by much = warning only, no delay)
BURST_WARNING_THRESHOLD = 1.5  # 1.5x limit = warning, no delay
BURST_DELAY_THRESHOLD = 2.0  # 2x limit = start applying delays

# State file location
STATE_FILE = Path(os.environ.get(
    "NINJAEXA_STATE_FILE",
    os.path.join(os.path.expanduser("~"), ".cache", "ninjaexa_rate_state.json")
))

# Disable rate limiting entirely (for testing)
RATE_LIMITING_DISABLED = os.environ.get("NINJAEXA_NO_RATE_LIMIT", "").lower() in ("1", "true", "yes")


# =============================================================================
# Rate Limiter State
# =============================================================================

@dataclass
class RateLimiterState:
    """Persistent state for the rate limiter."""
    
    # Rolling window of recent request timestamps
    timestamps: List[float] = field(default_factory=list)
    
    # Exponential backoff state
    penalty_level: int = 0  # 0 = no penalty, each level doubles delay
    last_violation_time: float = 0.0  # When last violation occurred
    last_request_time: float = 0.0  # When last request was made
    
    # Hourly/daily counters
    hourly_count: int = 0
    hourly_reset: float = 0.0  # Unix timestamp when hourly counter resets
    daily_count: int = 0
    daily_reset: float = 0.0  # Unix timestamp when daily counter resets
    
    # Metadata
    version: int = 1
    
    def to_dict(self) -> dict:
        """Convert to JSON-serializable dict."""
        return {
            "version": self.version,
            "timestamps": self.timestamps[-500:],  # Keep last 500 only
            "penalty_level": self.penalty_level,
            "last_violation_time": self.last_violation_time,
            "last_request_time": self.last_request_time,
            "hourly_count": self.hourly_count,
            "hourly_reset": self.hourly_reset,
            "daily_count": self.daily_count,
            "daily_reset": self.daily_reset,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "RateLimiterState":
        """Create from dict (handles missing/old fields gracefully)."""
        return cls(
            timestamps=data.get("timestamps", []),
            penalty_level=data.get("penalty_level", 0),
            last_violation_time=data.get("last_violation_time", 0.0),
            last_request_time=data.get("last_request_time", 0.0),
            hourly_count=data.get("hourly_count", 0),
            hourly_reset=data.get("hourly_reset", 0.0),
            daily_count=data.get("daily_count", 0),
            daily_reset=data.get("daily_reset", 0.0),
            version=data.get("version", 1),
        )


# =============================================================================
# State Persistence
# =============================================================================

def _load_state() -> RateLimiterState:
    """Load state from disk, or create fresh state if none exists."""
    try:
        if STATE_FILE.exists():
            with open(STATE_FILE, 'r') as f:
                data = json.load(f)
                return RateLimiterState.from_dict(data)
    except (json.JSONDecodeError, IOError, KeyError) as e:
        # Corrupted state file - start fresh
        pass
    return RateLimiterState()


def _save_state(state: RateLimiterState) -> None:
    """Save state to disk."""
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STATE_FILE, 'w') as f:
            json.dump(state.to_dict(), f)
    except IOError:
        pass  # Best effort - don't fail the request


# =============================================================================
# Rate Limiting Logic
# =============================================================================

def _count_requests_in_window(timestamps: List[float], window_seconds: float, now: float) -> int:
    """Count how many requests occurred within the time window."""
    cutoff = now - window_seconds
    return sum(1 for ts in timestamps if ts > cutoff)


def _calculate_current_penalty(state: RateLimiterState, now: float) -> float:
    """
    Calculate current penalty delay in seconds.
    
    Penalty decays over time if no violations occur.
    """
    if state.penalty_level == 0:
        return 0.0
    
    # Calculate decay based on time since last violation
    time_since_violation = now - state.last_violation_time
    decay_periods = time_since_violation / (PENALTY_DECAY_MINUTES * 60)
    
    # Each decay period halves the effective penalty level
    effective_level = state.penalty_level - decay_periods
    if effective_level <= 0:
        return 0.0
    
    # Calculate penalty: base * (multiplier ^ level)
    penalty = BASE_PENALTY_SECONDS * (PENALTY_MULTIPLIER ** (effective_level - 1))
    return min(penalty, MAX_PENALTY_SECONDS)


def _reset_counters_if_needed(state: RateLimiterState, now: float) -> None:
    """Reset hourly/daily counters if their windows have passed."""
    # Hourly reset
    if now >= state.hourly_reset:
        state.hourly_count = 0
        state.hourly_reset = now + 3600  # Reset in 1 hour
    
    # Daily reset
    if now >= state.daily_reset:
        state.daily_count = 0
        state.daily_reset = now + 86400  # Reset in 24 hours


def _prune_old_timestamps(timestamps: List[float], now: float) -> List[float]:
    """Remove timestamps older than 1 hour (we don't need them)."""
    cutoff = now - 3600
    return [ts for ts in timestamps if ts > cutoff]


def check_rate_limit() -> Tuple[bool, float, Optional[str]]:
    """
    Check if a request should be allowed, delayed, or blocked.
    
    Returns:
        (allowed, delay_seconds, message)
        - allowed: True if request can proceed (possibly after delay)
        - delay_seconds: How long to wait before proceeding (0 = no wait)
        - message: Warning/error message (None if all good)
    
    Call this BEFORE making an API request.
    """
    if RATE_LIMITING_DISABLED:
        return (True, 0.0, None)
    
    now = time.time()
    state = _load_state()
    
    # Prune old timestamps and reset counters
    state.timestamps = _prune_old_timestamps(state.timestamps, now)
    _reset_counters_if_needed(state, now)
    
    # Count requests in various windows
    req_1min = _count_requests_in_window(state.timestamps, 60, now)
    req_10min = _count_requests_in_window(state.timestamps, 600, now)
    
    # Check hard caps first (these are non-negotiable blocks)
    if state.hourly_count >= RATE_LIMIT_PER_HOUR:
        time_until_reset = state.hourly_reset - now
        return (False, 0.0, 
                f"[BLOCKED] Hourly limit reached ({RATE_LIMIT_PER_HOUR}/hour). "
                f"Resets in {int(time_until_reset/60)} minutes.")
    
    if state.daily_count >= RATE_LIMIT_PER_DAY:
        time_until_reset = state.daily_reset - now
        return (False, 0.0,
                f"[BLOCKED] Daily limit reached ({RATE_LIMIT_PER_DAY}/day). "
                f"Resets in {int(time_until_reset/3600)} hours.")
    
    # Calculate rate ratios
    ratio_1min = req_1min / RATE_LIMIT_PER_MINUTE if RATE_LIMIT_PER_MINUTE > 0 else 0
    ratio_10min = req_10min / RATE_LIMIT_PER_10_MIN if RATE_LIMIT_PER_10_MIN > 0 else 0
    max_ratio = max(ratio_1min, ratio_10min)
    
    # Calculate any existing penalty from previous violations
    current_penalty = _calculate_current_penalty(state, now)
    
    delay = 0.0
    message = None
    violation = False
    
    if max_ratio >= BURST_DELAY_THRESHOLD:
        # Severe abuse - apply exponential backoff
        violation = True
        state.penalty_level = min(state.penalty_level + 1, 10)  # Cap at level 10
        state.last_violation_time = now
        
        # Calculate new penalty
        new_penalty = BASE_PENALTY_SECONDS * (PENALTY_MULTIPLIER ** (state.penalty_level - 1))
        delay = min(new_penalty, MAX_PENALTY_SECONDS)
        
        message = (f"[RATE LIMITED] Too many requests ({req_1min}/min, {req_10min}/10min). "
                   f"Penalty level {state.penalty_level}: waiting {delay:.1f}s. "
                   f"Slow down to avoid longer delays.")
        
    elif max_ratio >= BURST_WARNING_THRESHOLD:
        # Approaching limit - warn but don't delay yet
        message = (f"[WARNING] High request rate ({req_1min}/min, {req_10min}/10min). "
                   f"Limit: {RATE_LIMIT_PER_MINUTE}/min. Slow down to avoid delays.")
        
        # Apply existing penalty if any (from previous violations)
        if current_penalty > 0:
            delay = current_penalty
            message += f" (Existing penalty: {delay:.1f}s delay)"
    
    elif current_penalty > 0:
        # Under limit but still serving penalty from earlier
        delay = current_penalty
        message = f"[COOLDOWN] Penalty from earlier abuse: {delay:.1f}s delay remaining."
    
    # If no violation this round and under warning threshold, decay penalty faster
    if not violation and max_ratio < 1.0 and state.penalty_level > 0:
        # Good behavior - accelerate decay
        time_since_violation = now - state.last_violation_time
        if time_since_violation > 60:  # At least 1 minute of good behavior
            state.penalty_level = max(0, state.penalty_level - 1)
    
    # Save state (will be committed after request in record_request)
    _save_state(state)
    
    return (True, delay, message)


def record_request() -> None:
    """
    Record that a request was made.
    Call this AFTER a successful API request.
    """
    if RATE_LIMITING_DISABLED:
        return
    
    now = time.time()
    state = _load_state()
    
    # Add timestamp
    state.timestamps.append(now)
    state.timestamps = _prune_old_timestamps(state.timestamps, now)
    
    # Increment counters
    _reset_counters_if_needed(state, now)
    state.hourly_count += 1
    state.daily_count += 1
    state.last_request_time = now
    
    _save_state(state)


def get_rate_status() -> dict:
    """
    Get current rate limiter status (for debugging/display).
    
    Returns dict with:
    - requests_1min: Requests in last minute
    - requests_10min: Requests in last 10 minutes
    - requests_hour: Requests this hour
    - requests_day: Requests today
    - penalty_level: Current exponential backoff level
    - current_delay: Delay that would be applied now
    - limits: Current limit configuration
    """
    now = time.time()
    state = _load_state()
    state.timestamps = _prune_old_timestamps(state.timestamps, now)
    _reset_counters_if_needed(state, now)
    
    return {
        "requests_1min": _count_requests_in_window(state.timestamps, 60, now),
        "requests_10min": _count_requests_in_window(state.timestamps, 600, now),
        "requests_hour": state.hourly_count,
        "requests_day": state.daily_count,
        "penalty_level": state.penalty_level,
        "current_delay": _calculate_current_penalty(state, now),
        "limits": {
            "per_minute": RATE_LIMIT_PER_MINUTE,
            "per_10min": RATE_LIMIT_PER_10_MIN,
            "per_hour": RATE_LIMIT_PER_HOUR,
            "per_day": RATE_LIMIT_PER_DAY,
        },
        "disabled": RATE_LIMITING_DISABLED,
    }


def reset_rate_limiter() -> None:
    """
    Reset the rate limiter state completely.
    Use with caution - only for testing or after fixing abuse issues.
    """
    try:
        if STATE_FILE.exists():
            STATE_FILE.unlink()
    except IOError:
        pass


# =============================================================================
# CLI Interface (for testing/debugging)
# =============================================================================

def main():
    """CLI for checking rate limiter status."""
    import argparse
    
    parser = argparse.ArgumentParser(description="NinjaExa Rate Limiter Status")
    parser.add_argument("--status", action="store_true", help="Show current status")
    parser.add_argument("--reset", action="store_true", help="Reset rate limiter state")
    parser.add_argument("--test", action="store_true", help="Test check (doesn't count)")
    args = parser.parse_args()
    
    if args.reset:
        reset_rate_limiter()
        print("[OK] Rate limiter state reset")
        return 0
    
    if args.test:
        allowed, delay, message = check_rate_limit()
        print(f"Allowed: {allowed}")
        print(f"Delay: {delay:.1f}s")
        print(f"Message: {message or '(none)'}")
        return 0 if allowed else 1
    
    # Default: show status
    status = get_rate_status()
    
    print("=== NinjaExa Rate Limiter Status ===")
    print()
    
    if status["disabled"]:
        print("[WARNING] Rate limiting is DISABLED (NINJAEXA_NO_RATE_LIMIT=1)")
        print()
    
    print(f"Requests (1 min):  {status['requests_1min']:3d} / {status['limits']['per_minute']}")
    print(f"Requests (10 min): {status['requests_10min']:3d} / {status['limits']['per_10min']}")
    print(f"Requests (hour):   {status['requests_hour']:3d} / {status['limits']['per_hour']}")
    print(f"Requests (day):    {status['requests_day']:4d} / {status['limits']['per_day']}")
    print()
    print(f"Penalty level: {status['penalty_level']} (0=none, higher=stricter)")
    
    if status['current_delay'] > 0:
        print(f"Current delay: {status['current_delay']:.1f}s")
    else:
        print("Current delay: none")
    
    print()
    print("Environment overrides:")
    print("  NINJAEXA_RATE_PER_MIN    - Limit per minute")
    print("  NINJAEXA_RATE_PER_10MIN  - Limit per 10 minutes")
    print("  NINJAEXA_RATE_PER_HOUR   - Limit per hour")
    print("  NINJAEXA_RATE_PER_DAY    - Limit per day")
    print("  NINJAEXA_NO_RATE_LIMIT   - Set to 1 to disable (testing only)")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
