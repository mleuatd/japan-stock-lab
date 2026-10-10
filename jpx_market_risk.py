#!/usr/bin/env python3
"""Source-dated JPX securities requiring a no-new-buy / controlled-exit policy.

NOTICE: This is a deliberately *incomplete* manually sourced subset, not an
exhaustive point-in-time JPX corporate-action feed. Other at-risk stocks may
still be present. A published warning is available from that session's CLOSE,
not that same day's OPEN (conservative timestamp assumption). Delisting dates
never retroactively ban prior trading days. Never assume that an EXIT fills.
"""
from dataclasses import dataclass
from datetime import date

@dataclass(frozen=True)
class Restriction:
    security_code: str  # J-Quants 5-character symbol
    published_on: str
    category: str
    source_url: str
    delists_on: str | None = None

    def __post_init__(self):
        for day in (self.published_on,self.delists_on):
            if day is not None:date.fromisoformat(day)
        if not (self.security_code.isdigit() and len(self.security_code)==5):
            raise ValueError("Expected J-Quants 5-digit code")
        if not self.source_url.startswith("https://www.jpx.co.jp/"):
            raise ValueError("Require official JPX source URL")

# Earliest source-dated listing-risk warning observed for each known security.
# Every entry MUST have an officially published source; not inferred from
# future missing prices (which would create lookahead bias).
VERIFIED_RESTRICTIONS=(
    Restriction("61730","2025-01-28","SPECIAL_CAUTION",
      "https://www.jpx.co.jp/news/1023/20250128-12.html",
      delists_on="2026-06-01"),
    Restriction("17260","2026-02-04","SUPERVISION",
      "https://www.jpx.co.jp/news/1023/20260204-11.html",
      delists_on="2026-06-01"),
    Restriction("62010","2026-05-12","DELISTING_DECIDED",
      "https://www.jpx.co.jp/news/1023/20260512-12.html",
      delists_on="2026-06-01"),
)

_RESTRICTIONS={r.security_code:r for r in VERIFIED_RESTRICTIONS}

def risk_as_of_close(code,session):
    """Return known risk by session CLOSE, never from a later announcement."""
    r=_RESTRICTIONS.get(code)
    return (r is not None and session>=r.published_on)

def risk_as_of_open(code,session):
    """Announcement is not safely assumed known at that day's opening."""
    r=_RESTRICTIONS.get(code)
    return r is not None and (session>r.published_on or
                              (r.delists_on is not None and session>=r.delists_on))

def risk_reason(code,session):
    r=_RESTRICTIONS.get(code)
    return r.category if r is not None and risk_as_of_close(code,session) else None
