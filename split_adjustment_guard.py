"""Fail-closed J-Quants stock-split/reverse-split data quality boundary.

Private Neon SQL views in sql/015_split_adjustment_integrity.sql validate
each non-unit AdjFactor against the jump in adjusted-close/close ratios.
Confirmed split events are *not* thrown away. Unknown or inconsistent
split-boundary stocks are excluded from all affected historical research.
Other corporate actions and historical API adjustment revisions remain unverified.
"""
from pathlib import Path

GUARD_VERSION = "jquants-split-guard-v1"
TOLERANCE = 0.005


def inspect_guard(conn):
    """Returns (blocked security codes, non-sensitive aggregate statistics).

    A missing view, empty/unreliable scan or inconsistencies in its reported
    counts is a hard failure, not silent permission to include doubtful data.
    """
    with conn.cursor() as cur:
        cur.execute("""SELECT adjustment_event_count,verified_event_count,
                       unverified_event_count,verified_tickers,excluded_tickers
                       FROM split_adjustment_integrity_summary""")
        row = cur.fetchone()
        if not row:
            raise ValueError("Missing corporate-action integrity report")
        events, verified, unknown, confirmed_codes, blocked_count = (
            int(v) for v in row
        )
        if events <= 0 or verified < 0 or unknown < 0 or events != verified + unknown:
            raise ValueError("Incomplete J-Quants split integrity scan")
        cur.execute("SELECT security_code FROM split_adjustment_blocklist")
        blocked = {str(r[0]) for r in cur.fetchall()}
    if len(blocked) != blocked_count or len(blocked) > unknown:
        raise ValueError("Corporate-action blocklist/report mismatch")
    return blocked, {
        "guard_version": GUARD_VERSION,
        "adjustment_events": events,
        "verified_events": verified,
        "unverified_events": unknown,
        "verified_tickers": confirmed_codes,
        "excluded_tickers": blocked_count,
    }


def split_transition_ok(previous_ratio, current_ratio, factor):
    """Match current ex-date factor to adjacent history within fixed tolerance.

    The DB view performs the same check using precise NUMERIC; this helper
    allows deterministic regression tests of fractional split / reverse split.
    """
    import math
    vals = (previous_ratio, current_ratio, factor)
    if any(v is None or not isinstance(v, (int, float)) or
           not math.isfinite(v) or v <= 0 for v in vals):
        return None
    return abs(previous_ratio / current_ratio / factor - 1) <= TOLERANCE
