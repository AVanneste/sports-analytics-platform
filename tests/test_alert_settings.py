import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from odds_alerts import wanted  # noqa: E402


def test_settings_filters():
    settings = json.loads((ROOT / "alerts_settings.json").read_text())
    edge = {"sport": "Soccer", "book": "napoleon", "market": "total", "price": 2.1, "units": "Corners", "period": 1}
    assert wanted(edge, settings)
    assert not wanted({**edge, "price": 1.2}, settings)  # under min_odds
    assert not wanted(edge, {**settings, "corners": False})
    assert not wanted(edge, {**settings, "first_half": False})
    assert not wanted(edge, {**settings, "books": ["unibet"]})
    assert not wanted(edge, {**settings, "sports": ["Tennis"]})


def test_stake_in_euros_with_a_bankroll():
    from odds_alerts import stake_text
    assert stake_text(0.016, 500) == "stake €8 (1.6%)"
    assert stake_text(0.016, 0) == "stake 1.6%"
