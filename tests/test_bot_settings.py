import json
from pathlib import Path

from sports_common.bot_settings import apply

DEFAULTS = json.loads((Path(__file__).resolve().parent.parent / "alerts_settings.json").read_text())


def test_set_values_of_each_type_and_reset():
    o, replies = apply(["/set min_ev_pct 3.5", "/set corners off", "/set sports soccer tennis",
                        "/set min_pinnacle_limit soccer 500", "/set max_alerts_per_run 5"], DEFAULTS, {})
    assert o == {"min_ev_pct": 3.5, "corners": False, "sports": ["Soccer", "Tennis"],
                 "min_pinnacle_limit": {**DEFAULTS["min_pinnacle_limit"], "Soccer": 500.0}, "max_alerts_per_run": 5}
    assert all(r.startswith("⚙️") for r in replies)
    o2, replies = apply(["/set corners maybe", "/set nonsense 1", "/settings"], DEFAULTS, o)
    assert o2 == o and replies[0].startswith("⚠️") and replies[1].startswith("⚠️") and "min_ev_pct: 3.5 (changed)" in replies[2]
    assert apply(["/reset"], DEFAULTS, o)[0] == {}
