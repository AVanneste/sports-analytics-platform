"""Rolling momentum, shot efficiency, corners, cards, rest days, and venue-specific form tracker."""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional
from collections import defaultdict


class TeamFormTracker:
    """Maintains chronological match logs and rolling metrics per team."""

    def __init__(self):
        self.team_history = defaultdict(list)
        self.home_history = defaultdict(list)
        self.away_history = defaultdict(list)

    def record_match(
        self,
        date: pd.Timestamp,
        home_team: str,
        away_team: str,
        fthg: int,
        ftag: int,
        hs: Optional[float] = None,
        as_: Optional[float] = None,
        hst: Optional[float] = None,
        ast: Optional[float] = None,
        hc: Optional[float] = None,
        ac: Optional[float] = None,
        hf: Optional[float] = None,
        af: Optional[float] = None,
        hy: Optional[float] = None,
        ay: Optional[float] = None,
        hr: Optional[float] = None,
        ar: Optional[float] = None,
    ):
        """Record completed match into team match logs."""
        if fthg > ftag:
            home_pts, away_pts = 3, 0
            home_res, away_res = "W", "L"
        elif fthg == ftag:
            home_pts, away_pts = 1, 1
            home_res, away_res = "D", "D"
        else:
            home_pts, away_pts = 0, 3
            home_res, away_res = "L", "W"

        h_y = hy if hy is not None and not np.isnan(hy) else 1.8
        a_y = ay if ay is not None and not np.isnan(ay) else 2.0
        h_r = hr if hr is not None and not np.isnan(hr) else 0.05
        a_r = ar if ar is not None and not np.isnan(ar) else 0.08
        h_f = hf if hf is not None and not np.isnan(hf) else 11.0
        a_f = af if af is not None and not np.isnan(af) else 11.5
        h_c = hc if hc is not None and not np.isnan(hc) else 5.2
        a_c = ac if ac is not None and not np.isnan(ac) else 4.5

        home_record = {
            "date": date,
            "venue": "H",
            "opponent": away_team,
            "gf": fthg,
            "ga": ftag,
            "pts": home_pts,
            "res": home_res,
            "shots_for": hs if hs is not None and not np.isnan(hs) else 12.5,
            "shots_against": as_ if as_ is not None and not np.isnan(as_) else 11.0,
            "sot_for": hst if hst is not None and not np.isnan(hst) else 4.5,
            "sot_against": ast if ast is not None and not np.isnan(ast) else 3.5,
            "corners_for": h_c,
            "corners_against": a_c,
            "fouls_for": h_f,
            "fouls_against": a_f,
            "yellows_for": h_y,
            "yellows_against": a_y,
            "reds_for": h_r,
            "reds_against": a_r,
            "cards_for": h_y + h_r,
            "cards_against": a_y + a_r,
        }

        away_record = {
            "date": date,
            "venue": "A",
            "opponent": home_team,
            "gf": ftag,
            "ga": fthg,
            "pts": away_pts,
            "res": away_res,
            "shots_for": as_ if as_ is not None and not np.isnan(as_) else 11.0,
            "shots_against": hs if hs is not None and not np.isnan(hs) else 12.5,
            "sot_for": ast if ast is not None and not np.isnan(ast) else 3.5,
            "sot_against": hst if hst is not None and not np.isnan(hst) else 4.5,
            "corners_for": a_c,
            "corners_against": h_c,
            "fouls_for": a_f,
            "fouls_against": h_f,
            "yellows_for": a_y,
            "yellows_against": h_y,
            "reds_for": a_r,
            "reds_against": h_r,
            "cards_for": a_y + a_r,
            "cards_against": h_y + h_r,
        }

        self.team_history[home_team].append(home_record)
        self.team_history[away_team].append(away_record)

        self.home_history[home_team].append(home_record)
        self.away_history[away_team].append(away_record)

    def get_team_rolling_features(self, team: str, current_date: pd.Timestamp, n_matches: int = 5) -> Dict[str, float]:
        """Compute rolling statistics for a team prior to the current match."""
        history = [m for m in self.team_history[team] if m["date"] < current_date]
        if not history:
            return {
                f"ppg_last{n_matches}": 1.35,
                f"win_rate_last{n_matches}": 0.35,
                f"draw_rate_last{n_matches}": 0.25,
                f"loss_rate_last{n_matches}": 0.40,
                f"gf_per_game_last{n_matches}": 1.35,
                f"ga_per_game_last{n_matches}": 1.35,
                f"gd_per_game_last{n_matches}": 0.0,
                f"tsr_last{n_matches}": 0.50,
                f"sotr_last{n_matches}": 0.50,
                f"corners_for_last{n_matches}": 5.0,
                f"corners_against_last{n_matches}": 4.8,
                f"corners_diff_last{n_matches}": 0.2,
                f"fouls_for_last{n_matches}": 11.2,
                f"fouls_against_last{n_matches}": 11.2,
                f"cards_for_last{n_matches}": 2.1,
                f"cards_against_last{n_matches}": 2.1,
                "days_rest": 7.0,
                "matches_last_21d": 3.0,
            }

        recent = history[-n_matches:]
        k = len(recent)

        pts = sum(m["pts"] for m in recent)
        wins = sum(1 for m in recent if m["res"] == "W")
        draws = sum(1 for m in recent if m["res"] == "D")
        losses = sum(1 for m in recent if m["res"] == "L")

        gf = sum(m["gf"] for m in recent)
        ga = sum(m["ga"] for m in recent)

        shots_for = sum(m["shots_for"] for m in recent)
        shots_against = sum(m["shots_against"] for m in recent)
        tsr = shots_for / (shots_for + shots_against + 1e-5)

        sot_for = sum(m["sot_for"] for m in recent)
        sot_against = sum(m["sot_against"] for m in recent)
        sotr = sot_for / (sot_for + sot_against + 1e-5)

        corners_for = sum(m["corners_for"] for m in recent) / k
        corners_against = sum(m["corners_against"] for m in recent) / k
        corners_diff = corners_for - corners_against

        fouls_for = sum(m["fouls_for"] for m in recent) / k
        fouls_against = sum(m["fouls_against"] for m in recent) / k
        cards_for = sum(m["cards_for"] for m in recent) / k
        cards_against = sum(m["cards_against"] for m in recent) / k

        last_match_date = history[-1]["date"]
        days_rest = max(1.0, (current_date - last_match_date).total_seconds() / 86400.0)
        matches_21d = sum(1 for m in history if (current_date - m["date"]).total_seconds() / 86400.0 <= 21.0)

        return {
            f"ppg_last{n_matches}": pts / k,
            f"win_rate_last{n_matches}": wins / k,
            f"draw_rate_last{n_matches}": draws / k,
            f"loss_rate_last{n_matches}": losses / k,
            f"gf_per_game_last{n_matches}": gf / k,
            f"ga_per_game_last{n_matches}": ga / k,
            f"gd_per_game_last{n_matches}": (gf - ga) / k,
            f"tsr_last{n_matches}": tsr,
            f"sotr_last{n_matches}": sotr,
            f"corners_for_last{n_matches}": corners_for,
            f"corners_against_last{n_matches}": corners_against,
            f"corners_diff_last{n_matches}": corners_diff,
            f"fouls_for_last{n_matches}": fouls_for,
            f"fouls_against_last{n_matches}": fouls_against,
            f"cards_for_last{n_matches}": cards_for,
            f"cards_against_last{n_matches}": cards_against,
            "days_rest": min(30.0, days_rest),
            "matches_last_21d": float(matches_21d),
        }

    def get_venue_specific_form(self, team: str, current_date: pd.Timestamp, venue: str = "H", n_matches: int = 5) -> Dict[str, float]:
        """Compute home-specific or away-specific rolling form."""
        venue_history = self.home_history[team] if venue == "H" else self.away_history[team]
        history = [m for m in venue_history if m["date"] < current_date]
        prefix = "home" if venue == "H" else "away"

        if not history:
            return {
                f"{prefix}_ppg_last{n_matches}": 1.5 if venue == "H" else 1.1,
                f"{prefix}_gf_last{n_matches}": 1.5 if venue == "H" else 1.1,
                f"{prefix}_ga_last{n_matches}": 1.1 if venue == "H" else 1.5,
                f"{prefix}_corners_last{n_matches}": 5.5 if venue == "H" else 4.3,
                f"{prefix}_cards_last{n_matches}": 1.9 if venue == "H" else 2.2,
            }

        recent = history[-n_matches:]
        k = len(recent)
        pts = sum(m["pts"] for m in recent)
        gf = sum(m["gf"] for m in recent)
        ga = sum(m["ga"] for m in recent)
        corners = sum(m["corners_for"] for m in recent) / k
        cards = sum(m["cards_for"] for m in recent) / k

        return {
            f"{prefix}_ppg_last{n_matches}": pts / k,
            f"{prefix}_gf_last{n_matches}": gf / k,
            f"{prefix}_ga_last{n_matches}": ga / k,
            f"{prefix}_corners_last{n_matches}": corners,
            f"{prefix}_cards_last{n_matches}": cards,
        }
