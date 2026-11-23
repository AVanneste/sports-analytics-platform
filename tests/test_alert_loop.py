import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from odds_alerts import MAX_GAP, DeliveryFailed, loop  # noqa: E402


class Clock:
    """A fake monotonic clock: scans advance it by their duration, sleeping by the wait."""

    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds


def run(scan, minutes, every=60, state=None):
    clock, saved, starts = Clock(), [], []
    state = {} if state is None else state

    def timed(st, report):
        starts.append(clock.t)
        scan(st, report, len(starts))
        clock.t += 10                                   # a scan takes 10 s

    n = loop(timed, state, minutes, every, lambda st: saved.append(dict(st)), sleep=clock.sleep, clock=clock)
    return n, state, saved, starts


def test_scans_back_to_back_with_one_state_and_a_save_after_each():
    def scan(st, report, i):
        st.setdefault("received", {})[f"alert{i}"] = True
    n, state, saved, starts = run(scan, minutes=2.5)
    assert n == 3 and starts == [0, 60, 120]                     # one start per minute, stops before 150 s
    assert state["received"] == {"alert1": True, "alert2": True, "alert3": True}
    assert len(saved) == 3


def test_one_scan_without_a_loop_and_failures_still_raise():
    n, _, saved, _ = run(lambda st, report, i: None, minutes=0)
    assert n == 1 and len(saved) == 1
    def broken(st, report, i):
        raise RuntimeError("feed down")
    with pytest.raises(RuntimeError):
        run(broken, minutes=0)


def test_gap_doubles_after_pinnacle_refuses_and_shrinks_back():
    def scan(st, report, i):
        report["pinnacle_refused"] = 2 if i in (2, 3) else 0
    _, _, _, starts = run(scan, minutes=15)
    gaps = [round(b - a, 1) for a, b in zip(starts, starts[1:])][:6]
    assert gaps == [60, 120, 240, 192, 153.6, 122.9]
    assert MAX_GAP == 300


def test_failed_delivery_undoes_its_scan_but_keeps_the_inbox_offset():
    def scan(st, report, i):
        st.setdefault("received", {})[f"alert{i}"] = True
        st["tg_offset"] = 100 + i
        if i == 2:
            raise DeliveryFailed("telegram down")
    state = {}
    with pytest.raises(DeliveryFailed):
        run(scan, minutes=5, state=state)
    assert state == {"received": {"alert1": True}, "tg_offset": 102}   # alert2 will be sent again next run


def test_other_failures_in_a_loop_are_undone_and_the_loop_goes_on():
    def scan(st, report, i):
        st.setdefault("received", {})[f"alert{i}"] = True
        if i == 2:
            raise ConnectionError("Napoleon timed out")
    n, state, saved, _ = run(scan, minutes=2.5)
    assert n == 3 and state["received"] == {"alert1": True, "alert3": True} and len(saved) == 2
