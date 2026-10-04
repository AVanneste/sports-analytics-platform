"""Shared request settings for The Odds API (football and tennis clients).

The Odds API charges (markets x regions) credits per /odds request, except when the response is
empty. Asking only the European region (Pinnacle and the European books) and only for events
starting within ODDS_WINDOW_HOURS keeps a daily run inside the free 500 credits a month.
"""
from datetime import datetime, timedelta, timezone
from typing import Dict

ODDS_REGIONS = "eu"
ODDS_WINDOW_HOURS = 36


def odds_window_params(hours: int = ODDS_WINDOW_HOURS) -> Dict[str, str]:
    """commenceTimeFrom/To query parameters for events starting within the next ``hours``."""
    now = datetime.now(timezone.utc).replace(microsecond=0)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return {"commenceTimeFrom": now.strftime(fmt), "commenceTimeTo": (now + timedelta(hours=hours)).strftime(fmt)}
