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


def test_skip_applies_to_the_full_match_main_score_only():
    settings = json.loads((ROOT / "alerts_settings.json").read_text())
    side = {"sport": "Soccer", "book": "napoleon", "market": "moneyline", "price": 2.0, "units": None, "period": 0}
    assert not wanted(side, settings)                                   # lineup-time alerts: -2.6% at the close
    assert wanted({**side, "sport": "Tennis"}, settings)
    assert wanted({**side, "market": "total", "units": "Corners"}, settings)
    assert wanted({**side, "sport": "Basketball", "market": "spread", "period": 1}, settings)
    assert wanted(side, {**settings, "skip": []})


def _edge(sel, ev, price=2.0, **k):
    return {"event_id": 1, "market": "moneyline", "period": 0, "units": None, "side": None, "line": None, "selection": sel,
            "start": "2026-11-12T18:45:00Z", "stake": 0.01, "book": "napoleon", "price": price, "ev": ev, "sport": "Tennis", **k}


def test_everything_is_collected_and_the_user_settings_only_flag_what_is_sent():
    from datetime import datetime, timezone
    from odds_alerts import plan_alerts
    file = json.loads((ROOT / "alerts_settings.json").read_text())
    collect = file["collect"]
    settings = {**{k: v for k, v in file.items() if k != "collect"}, "min_ev_pct": 4.0, "max_odds": 2.25, "books": ["napoleon"], "skip": []}
    now = datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    edges = [_edge("home", 0.06), _edge("away", 0.015), _edge("draw", 0.05, price=3.4), _edge("home", 0.05, book="unibet", market="total", line=2.5)]
    state = {}
    sent, rows = plan_alerts(edges, {}, state, collect, settings, now, min_ev=0.04)
    assert [(a["selection"], a["market"]) for a in sent] == [("home", "moneyline")]
    flags = {(r["selection"], r["market"], r["book"]): r["sent"] for r in rows}
    assert flags[("home", "moneyline", "napoleon")] is True        # passes every user filter
    assert flags[("away", "moneyline", "napoleon")] is False       # 1.5% EV: collected, not sent
    assert flags[("draw", "moneyline", "napoleon")] is False       # odds 3.4 over the user's 2.25: collected, not sent
    assert flags[("home", "total", "unibet")] is False             # a book the user switched off: collected, not sent
    # an alert first seen under the user's bar can still reach them when its EV grows
    sent2, rows2 = plan_alerts([_edge("away", 0.07)], {}, state, collect, settings, now, min_ev=0.04)
    assert [a["selection"] for a in sent2] == ["away"] and rows2[0]["sent"] is True


def test_archive_header_is_widened_in_place(tmp_path):
    from sports_common.odds_archive import append_rows
    append_rows([{"captured_at": "2026-11-12T10:00:00Z", "a": 1}], ["captured_at", "a"], tmp_path)
    path = append_rows([{"captured_at": "2026-11-12T11:00:00Z", "a": 2, "sent": False}], ["captured_at", "a", "sent"], tmp_path)
    lines = path.read_text().strip().splitlines()
    assert lines == ["captured_at,a,sent", "2026-11-12T10:00:00Z,1,", "2026-11-12T11:00:00Z,2,False"]


def test_payload_and_report_ignore_unsent_rows():
    from sports_common.edges import web_payload
    a = {"event_id": 1, "sport": "Soccer", "start": "2026-11-13T18:45:00Z", "home": "A", "away": "B", "market": "moneyline",
         "period": 0, "units": None, "side": None, "line": None, "selection": "home", "book": "napoleon", "price": 2.0,
         "ev": 0.05, "fair_prob": 0.5, "close_prob": 0.5, "books": "{}", "captured_at": "2026-11-12T10:00:00Z"}
    p = web_payload({"x": {**a, "sent": False}, "y": {**a, "selection": "away", "sent": True}}, [], datetime_now())
    assert [o["selection"] for o in p["open"]] == ["away"]


def datetime_now():
    from datetime import datetime, timezone
    return datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
