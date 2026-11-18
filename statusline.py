#!/usr/bin/env python3
"""Claude Code status line.

Reads the status line JSON payload from stdin and prints one colorized line.
Never crashes: a segment that fails is skipped, and if nothing can be shown
it prints the model name or "Claude Code".
"""
import json
import os
import sys
import time

# Context color: yellow/red from these absolute token counts, and red from
# CTX_PCT_RED percent of the window regardless of count (small-window models).
CTX_YELLOW = 100_000
CTX_RED = 200_000
CTX_PCT_RED = 80

# Rate-limit color: percent of the 5h / 7d quota used.
RL_YELLOW = 50
RL_RED = 80

GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
DIM = "\033[2m"
RESET = "\033[0m"

SEP = f" {DIM}│{RESET} "


def fmt_tokens(n):
    if n >= 999_500:  # anything lower would round to "1000k"
        return f"{n / 1e6:.1f}".removesuffix(".0") + "M"
    if n >= 1000:
        return f"{n / 1000:.0f}k"
    return str(n)


def fmt_duration(seconds):
    hours, minutes = divmod(max(int(seconds), 0) // 60, 60)
    if hours >= 24:
        return f"{hours // 24}d{hours % 24}h"
    if hours:
        return f"{hours}h{minutes:02d}m"
    return f"{minutes}m"


def threshold_color(value, yellow, red):
    if value >= red:
        return RED
    if value >= yellow:
        return YELLOW
    return ""


def segment_dir(data):
    """Directory the session was started in, with the home folder as ~."""
    ws = data.get("workspace") or {}
    path = ws.get("project_dir") or ws.get("current_dir") or data.get("cwd")
    if not path:
        return None
    home = os.path.expanduser("~")
    if path == home or path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def segment_model(data):
    model = data.get("model") or {}
    name = model.get("display_name") or model.get("id")
    if not name:
        return None
    effort = (data.get("effort") or {}).get("level")
    return f"{name} {DIM}{effort}{RESET}" if effort else name


def segment_context(data):
    cw = data.get("context_window") or {}
    usage = cw.get("current_usage")
    if not usage:
        return None
    tokens = sum(
        usage.get(key) or 0
        for key in ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    )
    color = threshold_color(tokens, CTX_YELLOW, CTX_RED) or GREEN
    text = f"ctx {fmt_tokens(tokens)}"
    size = cw.get("context_window_size")
    if size:
        pct = tokens / size * 100
        text += f"/{fmt_tokens(size)} ({pct:.0f}%)"
        if pct >= CTX_PCT_RED:
            color = RED
    return f"{color}{text}{RESET}"


def segment_rate_limits(data):
    limits = data.get("rate_limits") or {}
    now = time.time()
    parts = []
    for label, key in (("5h", "five_hour"), ("7d", "seven_day")):
        limit = limits.get(key) or {}
        pct = limit.get("used_percentage")
        if pct is None:
            continue
        text = f"{label} {pct:.0f}%"
        resets_at = limit.get("resets_at")
        if resets_at is not None:
            text += f" ↺ {fmt_duration(resets_at - now)}"
        color = threshold_color(pct, RL_YELLOW, RL_RED)
        parts.append(f"{color}{text}{RESET}" if color else text)
    return " · ".join(parts)


def segment_lines(data):
    cost = data.get("cost") or {}
    added = cost.get("total_lines_added") or 0
    removed = cost.get("total_lines_removed") or 0
    if not (added or removed):
        return None
    return f"{DIM}+{added} −{removed}{RESET}"


SEGMENTS = (segment_dir, segment_model, segment_context, segment_rate_limits, segment_lines)


def safe(fn, data):
    try:
        return fn(data)
    except Exception:
        return None


def main():
    data = {}
    try:
        data = json.load(sys.stdin)
        segments = (safe(fn, data) for fn in SEGMENTS)
        print(SEP.join(filter(None, segments)) or "Claude Code")
    except Exception:
        print(safe(segment_model, data) or "Claude Code")


if __name__ == "__main__":
    main()
