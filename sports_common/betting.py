"""Betting arithmetic shared by both sports."""
from typing import Optional

# Kelly stakes are recorded as currency on this notional bankroll (tennis has always used 1000).
NOTIONAL_BANKROLL = 1000.0


def bet_pnl(stake: float, odds: Optional[float], won: Optional[bool]) -> float:
    """Profit of a settled single at decimal ``odds``: stake*(odds-1) if won, -stake if lost, 0 if no bet."""
    if won is None or not stake or not odds or odds <= 1.0:
        return 0.0
    return round(stake * (odds - 1.0), 2) if won else round(-stake, 2)
