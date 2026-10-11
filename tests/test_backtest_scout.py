import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from backtest_scout import parse_history, value_at  # noqa: E402


def test_value_history_reads_the_value_at_a_date():
    data = {"id": 7, "birthDate": {"utcTime": "2004-03-02T00:00:00Z"},
            "marketValues": {"values": [{"date": "2025-07-01T00:00:00Z", "value": 900_000},
                                        {"date": "2025-01-01T00:00:00Z", "value": 400_000},
                                        {"date": "2026-10-01T00:00:00Z", "value": 2_500_000}]}}
    h = parse_history(data)
    assert h["birth_date"] == "2004-03-02" and h["values"][0] == ("2025-01-01", 400_000)  # sorted by date
    assert value_at(h["values"], "2025-06-01") == 400_000
    assert value_at(h["values"], "2024-12-01") is None
