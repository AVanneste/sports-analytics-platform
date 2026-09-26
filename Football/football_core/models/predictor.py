"""Master Predictor Engine for Match Outcomes, Goals, Corners, Cards, Referee Analytics & European Cups."""
import logging
from typing import Dict, Any, Optional, List
import numpy as np
import pandas as pd
from scipy.stats import poisson, nbinom

from football_core.config import LEAGUES, MIN_VALUE_THRESHOLD, MAX_VALUE_ODDS, MIN_VALUE_PROB, DEFAULT_KELLY_FRACTION, MODELS_DIR
from football_core.models.train import load_trained_bundle
from football_core.utils.helpers import (
    normalize_team_name,
    teams_match,
    calculate_ev,
    calculate_kelly_stake,
    remove_vig_multiplicative,
    strip_accents,
)

logger = logging.getLogger(__name__)

DOMESTIC_ALIASES = {
    "internazionale": "Inter",
    "inter milan": "Inter",
    "sporting cp": "Sp Lisbon",
    "sporting lisbon": "Sp Lisbon",
    "sporting": "Sp Lisbon",
    "braga": "Sp Braga",
    "sc braga": "Sp Braga",
    "racing genk": "Genk",
    "krc genk": "Genk",
    "standard liege": "Standard",
    "standard de liege": "Standard",
    "sint-truidense": "St Truiden",
    "sint truidense": "St Truiden",
    "st. truiden": "St Truiden",
    "union st.-gilloise": "St. Gilloise",
    "union sg": "St. Gilloise",
    "royale union saint-gilloise": "St. Gilloise",
    "fc cologne": "FC Koln",
    "cologne": "FC Koln",
    "1. fc koln": "FC Koln",
    "koln": "FC Koln",
    "hamburg sv": "Hamburger SV",
    "hamburger": "Hamburger SV",
    "hsv": "Hamburger SV",
    "alavés": "Alaves",
    "deportivo alaves": "Alaves",
    "málaga": "Malaga",
    "malaga cf": "Malaga",
    "deportivo": "Dep La Coruna",
    "deportivo la coruna": "Dep La Coruna",
    "rc deportivo": "Dep La Coruna",
    "vitória de guimaraes": "Guimaraes",
    "vitoria de guimaraes": "Guimaraes",
    "vitoria sc": "Guimaraes",
    "nec nijmegen": "Nijmegen",
    "ajax amsterdam": "Ajax",
    "fortuna sittard": "For Sittard",
    "sc cambuur": "Cambuur",
    "cambuur leeuwarden": "Cambuur",
    "sc paderborn 07": "Paderborn",
    "paderborn 07": "Paderborn",
    "c.d. nacional": "Nacional",
    "cd nacional": "Nacional",
    "espanyol": "Espanol",
    "rcd espanyol": "Espanol",
    "coventry city": "Coventry",
    "hull city": "Hull",
}

EUROPEAN_RATINGS = {
    # Turkey (Super Lig)
    "galatasaray": 1750.0, "fenerbahce": 1730.0, "besiktas": 1660.0, "trabzonspor": 1590.0, "basaksehir": 1560.0,
    # Austria (Bundesliga)
    "salzburg": 1695.0, "rb salzburg": 1695.0, "red bull salzburg": 1695.0, "sturm graz": 1635.0, "lask linz": 1570.0, "lask": 1570.0, "rapid vienna": 1560.0,
    # Greece (Super League)
    "olympiacos": 1685.0, "paok": 1650.0, "aek athens": 1630.0, "panathinaikos": 1615.0, "aris": 1520.0, "ofi crete": 1480.0,
    # Czechia (First League)
    "slavia prague": 1715.0, "sparta prague": 1695.0, "viktoria plzen": 1640.0, "jablonec": 1490.0, "banik ostrava": 1510.0,
    # Croatia
    "dinamo zagreb": 1665.0, "hajduk split": 1565.0, "rijeka": 1550.0, "osijek": 1490.0,
    # Serbia
    "red star belgrade": 1635.0, "crvena zvezda": 1635.0, "partizan": 1570.0, "tsc backa topola": 1490.0,
    # Ukraine
    "shakhtar donetsk": 1675.0, "dynamo kyiv": 1640.0, "dnipro-1": 1500.0,
    # Denmark (Superliga)
    "f.c. kobenhavn": 1660.0, "fc copenhagen": 1660.0, "fc kobenhavn": 1660.0, "fc midtjylland": 1640.0, "fc nordsjaelland": 1570.0, "agf": 1535.0, "agf aarhus": 1535.0, "brondby": 1590.0, "silkeborg": 1520.0,
    # Norway (Eliteserien)
    "bodo/glimt": 1665.0, "sk brann": 1565.0, "brann": 1565.0, "viking fk": 1545.0, "viking": 1545.0, "molde": 1620.0, "rosenborg": 1530.0, "lillestrom": 1515.0,
    # Switzerland (Super League)
    "young boys": 1630.0, "fc lugano": 1555.0, "lugano": 1555.0, "servette": 1560.0, "fc thun": 1485.0, "fc zurich": 1540.0, "basel": 1570.0, "st. gallen": 1520.0,
    # Poland (Ekstraklasa)
    "lech poznan": 1585.0, "jagiellonia bialystok": 1565.0, "jagiellonia": 1565.0, "legia warsaw": 1575.0, "rakow": 1560.0,
    # Hungary
    "ferencvaros": 1625.0, "fehervar": 1470.0,
    # Slovakia
    "slovan bratislava": 1580.0, "spartak trnava": 1480.0,
    # Sweden (Allsvenskan)
    "malmo": 1610.0, "malmo ff": 1610.0, "djurgarden": 1540.0, "hacken": 1530.0, "elfsborg": 1540.0, "mjallby aif": 1520.0, "mjallby": 1520.0,
    # Cyprus
    "pafos": 1545.0, "pafos fc": 1545.0, "omonia nicosia": 1530.0, "omonia": 1530.0, "apoel nicosia": 1540.0, "apoel": 1540.0, "aris limassol": 1520.0,
    # Romania / Bulgaria
    "fcsb": 1550.0, "cfr cluj": 1530.0, "csu craiova": 1515.0, "universitatea craiova": 1515.0, "ludogorets": 1590.0, "cska sofia": 1505.0, "levski sofia": 1515.0,
    # Israel
    "maccabi tel aviv": 1560.0, "maccabi haifa": 1550.0, "hapoel be'er": 1530.0, "hapoel beer sheva": 1530.0,
    # Slovenia / Bosnia / Kazakhstan / Others
    "nk celje": 1485.0, "celje": 1485.0, "maribor": 1500.0, "olimpija ljubljana": 1490.0, "borac banja luka": 1440.0, "zrinski": 1460.0, "kups kuopio": 1460.0, "kups": 1460.0, "hjk helsinki": 1490.0,
    "kairat almaty": 1480.0, "astana": 1510.0, "sabah fk": 1450.0, "qarabag": 1610.0, "neftchi baku": 1470.0, "ararat-armenia": 1410.0, "pyunik": 1420.0,
    "egnatia": 1380.0, "partizani": 1390.0, "kauno zalgiris": 1370.0, "zalgiris": 1420.0, "iberia 1999": 1390.0, "dinamo tbilisi": 1440.0, "riga fc": 1430.0, "rfs": 1440.0,
    "lincoln red imps": 1350.0, "inter d'escaldes": 1320.0, "buducnost": 1380.0, "de cic": 1340.0, "the new saints": 1370.0, "shamrock rovers": 1450.0, "larne": 1360.0, "vikingur": 1380.0,
    # Secondary tier / League Cup entries
    "sunderland": 1590.0, "coventry city": 1580.0, "hull city": 1540.0, "racing santander": 1530.0, "deportivo": 1520.0, "dep la coruna": 1520.0, "malaga": 1510.0,
    "hamburg sv": 1590.0, "sc paderborn 07": 1520.0, "sv elversberg": 1480.0, "paris fc": 1520.0, "le mans": 1440.0, "falkirk": 1470.0, "partick thistle": 1420.0,
    "zulte-waregem": 1475.0, "lommel sk": 1450.0, "raal la louviere": 1420.0, "alverca": 1460.0, "torreense": 1440.0, "academico de viseu": 1430.0, "leixoes": 1410.0,
    "telstar": 1420.0, "ado den haag": 1490.0, "de graafschap": 1460.0, "cambuur": 1480.0, "volendam": 1470.0,
}


class FootballPredictor:
    """Multi-league inference engine combining Calibrated LightGBM, Dixon-Coles, Elo, Corners, and Cards."""

    def __init__(self):
        self.bundles: Dict[str, Dict[str, Any]] = {}
        self.multi_league_bundle: Optional[Dict[str, Any]] = None
        self._load_all_bundles()

    def _load_all_bundles(self):
        """Load pre-trained models and state pipelines for all leagues + unified multi-league bundle."""
        for league_key in LEAGUES.keys():
            if LEAGUES[league_key].get("is_cup"):
                continue
            bundle = load_trained_bundle(league_key)
            if bundle:
                self.bundles[league_key] = bundle
                logger.info(f"Loaded predictor bundle for {league_key}")
            else:
                logger.debug(f"No trained bundle found for {league_key}")

        # Load unified multi-league bundle if available
        ml_path = MODELS_DIR / "MultiLeague_bundle.joblib"
        if ml_path.exists():
            try:
                import joblib
                self.multi_league_bundle = joblib.load(ml_path)
                logger.info("Loaded unified Multi-League hierarchical bundle.")
            except Exception as e:
                logger.debug(f"Could not load multi-league bundle: {e}")

        # Load international model bundle if available
        intl_path = MODELS_DIR / "International_bundle.joblib"
        if intl_path.exists():
            try:
                import joblib
                self.bundles["International"] = joblib.load(intl_path)
                logger.info("Loaded predictor bundle for International")
            except Exception as e:
                logger.warning(f"Could not load International bundle from {intl_path}: {e}")

    def is_league_ready(self, league_key: str) -> bool:
        if LEAGUES.get(league_key, {}).get("is_international") or league_key == "International":
            return "International" in self.bundles
        if LEAGUES.get(league_key, {}).get("is_cup"):
            return len(self.bundles) > 0
        return league_key in self.bundles

    def get_known_teams(self, league_key: str) -> List[str]:
        """Return list of known teams with ratings in the league or across all leagues for cups."""
        if LEAGUES.get(league_key, {}).get("is_international") or league_key == "International":
            bundle = self.bundles.get("International")
            if bundle and hasattr(bundle.get("pipeline"), "elo_engine"):
                return sorted(list(bundle["pipeline"].elo_engine.ratings.keys()))
            return []

        if LEAGUES.get(league_key, {}).get("is_cup"):
            all_teams = set()
            for b in self.bundles.values():
                if hasattr(b.get("pipeline"), "elo_engine"):
                    all_teams.update(b["pipeline"].elo_engine.ratings.keys())
            return sorted(list(all_teams))

        bundle = self.bundles.get(league_key)
        if not bundle:
            return []
        pipeline = bundle["pipeline"]
        return sorted(list(pipeline.elo_engine.ratings.keys()))

    def get_known_referees(self, league_key: str) -> List[str]:
        """Return list of known referees for this league."""
        bundle = self.bundles.get(league_key)
        if not bundle:
            return []
        pipeline = bundle["pipeline"]
        return pipeline.referee_engine.get_all_known_referees()

    def _find_team_profile(self, team_name: str) -> Dict[str, Any]:
        """Search across all domestic bundles and European database to find a team's Elo, Attack, Defense, and Form."""
        norm = normalize_team_name(team_name)
        clean = strip_accents(norm).lower()
        t_clean = strip_accents(team_name).lower()
        alias = DOMESTIC_ALIASES.get(t_clean, DOMESTIC_ALIASES.get(clean))

        # 1. Search across domestic league pipelines
        for l_k, bundle in self.bundles.items():
            pipeline = bundle["pipeline"]
            ratings = pipeline.elo_engine.ratings
            target_key = None
            if norm in ratings:
                target_key = norm
            elif alias and alias in ratings:
                target_key = alias
            else:
                for r_name in ratings.keys():
                    if teams_match(norm, r_name) or (alias and teams_match(alias, r_name)):
                        target_key = r_name
                        break

            if target_key:
                elo = pipeline.elo_engine.get_rating(target_key)
                att = pipeline.dixon_coles_engine.attack_strengths.get(target_key, 0.0)
                dfn = pipeline.dixon_coles_engine.defense_strengths.get(target_key, 0.0)
                form = pipeline.form_tracker.get_team_rolling_features(target_key, pd.Timestamp.now(), n_matches=5)
                return {
                    "league": l_k,
                    "elo": float(elo),
                    "attack": float(att),
                    "defense": float(dfn),
                    "form": form or {},
                    "pipeline": pipeline,
                    "bundle": bundle,
                }

        # 2. Search International bundle for national teams
        intl_bundle = self.bundles.get("International")
        if intl_bundle and "pipeline" in intl_bundle:
            intl_pipe = intl_bundle["pipeline"]
            if hasattr(intl_pipe, "elo_engine"):
                res_name = intl_pipe.elo_engine.resolve_team(team_name)
                if res_name in intl_pipe.elo_engine.ratings:
                    elo = intl_pipe.elo_engine.get_rating(res_name)
                    form = intl_pipe.form_tracker.get_team_rolling_features(res_name, pd.Timestamp.now(), n_matches=5) if hasattr(intl_pipe, "form_tracker") else {}
                    return {
                        "league": "International",
                        "elo": float(elo),
                        "attack": 0.0,
                        "defense": 0.0,
                        "form": form or {},
                        "pipeline": intl_pipe,
                        "bundle": intl_bundle,
                    }

        # 3. Search European Club Ratings Database
        matched_elo = None
        if clean in EUROPEAN_RATINGS:
            matched_elo = EUROPEAN_RATINGS[clean]
        elif t_clean in EUROPEAN_RATINGS:
            matched_elo = EUROPEAN_RATINGS[t_clean]
        else:
            for k, elo_val in EUROPEAN_RATINGS.items():
                if teams_match(clean, k) or teams_match(t_clean, k):
                    matched_elo = elo_val
                    break

        if matched_elo is not None:
            att = round((matched_elo - 1500.0) / 400.0 * 0.45, 3)
            dfn = round(-(matched_elo - 1500.0) / 400.0 * 0.35, 3)
            return {
                "league": "European",
                "elo": float(matched_elo),
                "attack": float(att),
                "defense": float(dfn),
                "form": {"wins_last5": 3, "draws_last5": 1, "losses_last5": 1, "corners_for_last5": 5.1, "cards_for_last5": 2.0},
                "pipeline": None,
                "bundle": None,
            }

        # 4. Fallback baseline
        return {
            "league": "Other",
            "elo": 1500.0,
            "attack": 0.0,
            "defense": 0.0,
            "form": {},
            "pipeline": None,
            "bundle": None,
        }

    def _get_settled_tracker_matches(self) -> List[Dict[str, Any]]:
        """Fetch real settled matches from predictions tracker cache."""
        import json
        from pathlib import Path
        p = Path("Football/data/cache/predictions_tracker.json")
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return [d for d in data if d.get("status") == "settled" and d.get("actual_score")]
            except Exception:
                pass
        return []

    def get_team_recent_matches(self, league_key: str, team_name: str, n: int = 5) -> List[Dict[str, Any]]:
        """Return the last n matches for a team with score, opponent, venue, and result (merging 2026 real matches)."""
        from datetime import datetime
        is_intl = bool(LEAGUES.get(league_key, {}).get("is_international") or league_key == "International")
        if is_intl and "International" in self.bundles:
            bundle = self.bundles["International"]
            pipeline = bundle.get("pipeline")
            norm = pipeline.elo_engine.resolve_team(team_name) if (pipeline and hasattr(pipeline, "elo_engine")) else normalize_team_name(team_name)
        else:
            norm = normalize_team_name(team_name)
            bundle = self.bundles.get(league_key)
            if not bundle:
                profile = self._find_team_profile(team_name)
                pipeline = profile.get("pipeline")
            else:
                pipeline = bundle.get("pipeline")
        
        results = []
        if pipeline and hasattr(pipeline, "form_tracker"):
            hist = pipeline.form_tracker.team_history.get(norm, [])
            if not hist and norm != team_name:
                hist = pipeline.form_tracker.team_history.get(team_name, [])
            
            for m in hist:
                d_val = m.get("date")
                d_str = d_val.strftime("%Y-%m-%d") if isinstance(d_val, (pd.Timestamp, datetime)) else str(d_val)[:10]
                results.append({
                    "date": d_str,
                    "venue": "Home" if m.get("venue") == "H" else "Away",
                    "opponent": m.get("opponent", ""),
                    "score": f"{m.get('gf', 0)}-{m.get('ga', 0)}",
                    "gf": m.get("gf", 0),
                    "ga": m.get("ga", 0),
                    "res": m.get("res", "D" if m.get("gf", 0) == m.get("ga", 0) else ("W" if m.get("gf", 0) > m.get("ga", 0) else "L")),
                    "corners": m.get("corners_for", 0),
                    "cards": m.get("cards_for", 0),
                })

        # Merge newly settled 2026/2027 matches from tracker
        tracker_settled = self._get_settled_tracker_matches()
        for sm in tracker_settled:
            h_sm = sm.get("home_team", "")
            a_sm = sm.get("away_team", "")
            if teams_match(team_name, h_sm) or teams_match(team_name, a_sm):
                is_home = teams_match(team_name, h_sm)
                opp = a_sm if is_home else h_sm
                score_str = sm.get("actual_score", "0-0")
                try:
                    score_parts = score_str.split("-")
                    gf = int(score_parts[0]) if is_home else int(score_parts[1])
                    ga = int(score_parts[1]) if is_home else int(score_parts[0])
                except Exception:
                    gf, ga = 0, 0
                res = "W" if gf > ga else ("L" if ga > gf else "D")
                results.append({
                    "date": (sm.get("date") or "")[:10],
                    "venue": "Home" if is_home else "Away",
                    "opponent": opp,
                    "score": score_str,
                    "gf": gf,
                    "ga": ga,
                    "res": res,
                    "corners": int(sm.get("actual_corners") or 9) // 2,
                    "cards": int(sm.get("actual_cards") or 4) // 2,
                })

        # Deduplicate and sort by date descending
        seen_keys = set()
        unique_results = []
        for r in sorted(results, key=lambda x: str(x.get("date", "")), reverse=True):
            key = f"{r.get('date')}_{r.get('opponent')}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique_results.append(r)

        return unique_results[:n]

    def get_h2h_matches(self, league_key: str, home_team: str, away_team: str, n: int = 5) -> List[Dict[str, Any]]:
        """Return past head-to-head matches between home_team and away_team (merging 2026 matches)."""
        from datetime import datetime
        is_intl = bool(LEAGUES.get(league_key, {}).get("is_international") or league_key == "International")
        if is_intl and "International" in self.bundles:
            bundle = self.bundles["International"]
            pipeline = bundle.get("pipeline")
            norm_h = pipeline.elo_engine.resolve_team(home_team) if (pipeline and hasattr(pipeline, "elo_engine")) else normalize_team_name(home_team)
            norm_a = pipeline.elo_engine.resolve_team(away_team) if (pipeline and hasattr(pipeline, "elo_engine")) else normalize_team_name(away_team)
        else:
            norm_h = normalize_team_name(home_team)
            norm_a = normalize_team_name(away_team)
            bundle = self.bundles.get(league_key)
            if not bundle:
                profile = self._find_team_profile(home_team)
                pipeline = profile.get("pipeline")
            else:
                pipeline = bundle.get("pipeline")
            
        h2h_list = []
        if is_intl and pipeline and hasattr(pipeline, "h2h_tracker"):
            key = pipeline.h2h_tracker._get_key(norm_h, norm_a)
            hist = pipeline.h2h_tracker.matches.get(key, [])
            for m in hist:
                d_val = m.get("date")
                d_str = d_val.strftime("%Y-%m-%d") if isinstance(d_val, (pd.Timestamp, datetime)) else str(d_val)[:10]
                hg = int(m.get("fthg", 0))
                ag = int(m.get("ftag", 0))
                winner = m.get("home_team") if hg > ag else (m.get("away_team") if ag > hg else "Draw")
                h2h_list.append({
                    "date": d_str,
                    "home_team": m.get("home_team"),
                    "away_team": m.get("away_team"),
                    "score": f"{hg}-{ag}",
                    "h_score": hg,
                    "a_score": ag,
                    "winner": winner,
                })
        elif pipeline and hasattr(pipeline, "form_tracker"):
            hist = pipeline.form_tracker.team_history.get(norm_h, [])
            for m in hist:
                opp_norm = normalize_team_name(m.get("opponent", ""))
                if teams_match(opp_norm, norm_a) or teams_match(m.get("opponent", ""), away_team):
                    d_val = m.get("date")
                    d_str = d_val.strftime("%Y-%m-%d") if isinstance(d_val, (pd.Timestamp, datetime)) else str(d_val)[:10]
                    is_home = (m.get("venue") == "H")
                    h_score = m.get("gf") if is_home else m.get("ga")
                    a_score = m.get("ga") if is_home else m.get("gf")
                    
                    h2h_list.append({
                        "date": d_str,
                        "home_team": home_team if is_home else away_team,
                        "away_team": away_team if is_home else home_team,
                        "score": f"{h_score}-{a_score}",
                        "h_score": h_score,
                        "a_score": a_score,
                        "winner": home_team if m.get("res") == "W" else (away_team if m.get("res") == "L" else "Draw"),
                    })

        # Merge newly settled 2026/2027 matches from tracker
        tracker_settled = self._get_settled_tracker_matches()
        for sm in tracker_settled:
            h_sm = sm.get("home_team", "")
            a_sm = sm.get("away_team", "")
            is_match = (teams_match(home_team, h_sm) and teams_match(away_team, a_sm)) or (teams_match(home_team, a_sm) and teams_match(away_team, h_sm))
            if is_match:
                d_str = (sm.get("date") or "")[:10]
                score_str = sm.get("actual_score", "0-0")
                winner_str = sm.get("actual_winner", "Draw")
                h2h_list.append({
                    "date": d_str,
                    "home_team": h_sm,
                    "away_team": a_sm,
                    "score": score_str,
                    "h_score": int(score_str.split("-")[0]) if "-" in score_str else 0,
                    "a_score": int(score_str.split("-")[1]) if "-" in score_str else 0,
                    "winner": winner_str,
                })

        seen_keys = set()
        unique_h2h = []
        for r in sorted(h2h_list, key=lambda x: str(x.get("date", "")), reverse=True):
            key = f"{r.get('date')}_{r.get('home_team')}_{r.get('away_team')}"
            if key not in seen_keys:
                seen_keys.add(key)
                unique_h2h.append(r)

        return unique_h2h[:n]

    def get_team_summary_stats(self, league_key: str, team_name: str) -> Dict[str, Any]:
        """Compute key summary statistics (model Elo, form, avg goals, clean sheets, over 2.5, btts) strictly from real match data."""
        is_intl = bool(LEAGUES.get(league_key, {}).get("is_international") or league_key == "International")
        if is_intl and "International" in self.bundles:
            bundle = self.bundles["International"]
            pipeline = bundle.get("pipeline")
            norm = pipeline.elo_engine.resolve_team(team_name) if (pipeline and hasattr(pipeline, "elo_engine")) else normalize_team_name(team_name)
            elo = pipeline.elo_engine.get_rating(norm) if (pipeline and hasattr(pipeline, "elo_engine")) else None
            att = None
            dfn = None
        else:
            norm = normalize_team_name(team_name)
            bundle = self.bundles.get(league_key)
            if not bundle:
                profile = self._find_team_profile(team_name)
                pipeline = profile.get("pipeline")
                elo = profile.get("elo")
                att = profile.get("attack")
                dfn = profile.get("defense")
            else:
                pipeline = bundle.get("pipeline")
                elo = pipeline.elo_engine.get_rating(norm) if pipeline and hasattr(pipeline, "elo_engine") else None
                att = pipeline.dixon_coles_engine.attack_strengths.get(norm) if pipeline and hasattr(pipeline, "dixon_coles_engine") else None
                dfn = pipeline.dixon_coles_engine.defense_strengths.get(norm) if pipeline and hasattr(pipeline, "dixon_coles_engine") else None

        # Recent matches strictly from real matches (dataset + settled tracker)
        recent = self.get_team_recent_matches(league_key, team_name, n=5)
        form_seq = [m.get("res") for m in reversed(recent) if m.get("res")]

        hist = pipeline.form_tracker.team_history.get(norm, []) if (pipeline and hasattr(pipeline, "form_tracker")) else []
        if not hist and norm != team_name and pipeline and hasattr(pipeline, "form_tracker"):
            hist = pipeline.form_tracker.team_history.get(team_name, [])

        if hist:
            n_m = len(hist)
            avg_gf = sum(m.get("gf", 0) for m in hist) / n_m
            avg_ga = sum(m.get("ga", 0) for m in hist) / n_m
            clean_sheets = sum(1 for m in hist if m.get("ga", 0) == 0) / n_m
            btts_count = sum(1 for m in hist if m.get("gf", 0) > 0 and m.get("ga", 0) > 0) / n_m
            o25_count = sum(1 for m in hist if (m.get("gf", 0) + m.get("ga", 0)) > 2.5) / n_m
            avg_corners = sum(m.get("corners_for", 0) for m in hist if m.get("corners_for") is not None) / max(1, sum(1 for m in hist if m.get("corners_for") is not None))
            avg_cards = sum(m.get("cards_for", 0) for m in hist if m.get("cards_for") is not None) / max(1, sum(1 for m in hist if m.get("cards_for") is not None))
        else:
            avg_gf = None
            avg_ga = None
            clean_sheets = None
            btts_count = None
            o25_count = None
            avg_corners = None
            avg_cards = None

        if recent:
            n5 = len(recent)
            avg_gf_5 = sum(m.get("gf", 0) for m in recent) / n5
            avg_ga_5 = sum(m.get("ga", 0) for m in recent) / n5
        else:
            avg_gf_5 = None
            avg_ga_5 = None

        return {
            "elo": round(float(elo), 0) if elo is not None else None,
            "attack": round(float(att), 2) if att is not None else None,
            "defense": round(float(dfn), 2) if dfn is not None else None,
            "form": form_seq,
            "avg_gf_season": round(avg_gf, 2) if avg_gf is not None else None,
            "avg_ga_season": round(avg_ga, 2) if avg_ga is not None else None,
            "avg_gf_last5": round(avg_gf_5, 2) if avg_gf_5 is not None else None,
            "avg_ga_last5": round(avg_ga_5, 2) if avg_ga_5 is not None else None,
            "clean_sheet_pct": round(clean_sheets * 100, 1) if clean_sheets is not None else None,
            "btts_pct": round(btts_count * 100, 1) if btts_count is not None else None,
            "o25_pct": round(o25_count * 100, 1) if o25_count is not None else None,
            "avg_corners": round(avg_corners, 1) if avg_corners is not None else None,
            "avg_cards": round(avg_cards, 1) if avg_cards is not None else None,
            "matches_analyzed": len(hist) + len([m for m in recent if "2026" in str(m.get("date"))]),
        }

    @staticmethod
    def calibrate_corners_expectancy(
        h_corn_for: float,
        h_corn_against: float,
        a_corn_for: float,
        a_corn_against: float,
        elo_diff: float = 0.0,
    ) -> tuple:
        """
        Empirical Bayes regressed corners expectation & Negative Binomial overdispersed probabilities.
        Baseline from 5,521 European league matches: Home 5.50, Away 4.52, Overdispersion phi=1.20.
        Returns: (exp_total_corners, prob_o95, prob_u95, prob_o105)
        """
        # 1. Regress noisy rolling 5-game sample towards historical league baselines
        h_att = 0.35 * (h_corn_for or 5.50) + 0.65 * 5.50
        a_def = 0.35 * (a_corn_against or 5.50) + 0.65 * 5.50
        a_att = 0.35 * (a_corn_for or 4.52) + 0.65 * 4.52
        h_def = 0.35 * (h_corn_against or 4.52) + 0.65 * 4.52

        # 2. Possession & favorite modulation (dominant favorites generate more corners, but suppress opponents)
        elo_adj = float(np.clip(elo_diff / 400.0, -1.0, 1.0))
        proj_h = (h_att + a_def) / 2.0 + elo_adj * 0.55
        proj_a = (a_att + h_def) / 2.0 - elo_adj * 0.45

        proj_h = float(np.clip(proj_h, 3.2, 7.2))
        proj_a = float(np.clip(proj_a, 2.2, 5.8))
        exp_total = float(np.clip(proj_h + proj_a, 8.2, 11.8))

        # 3. Negative Binomial distribution for overdispersion (phi=1.20)
        phi = 1.20
        p = 1.0 / phi
        n = exp_total * p / (1.0 - p)
        p_o95 = float(np.clip(1.0 - nbinom.cdf(9, n, p), 0.15, 0.72))
        p_u95 = float(1.0 - p_o95)
        p_o105 = float(np.clip(1.0 - nbinom.cdf(10, n, p), 0.10, 0.63))

        return round(exp_total, 1), round(p_o95, 3), round(p_u95, 3), round(p_o105, 3)

    @staticmethod
    def calibrate_cards_expectancy(
        h_cards_for: float,
        h_cards_against: float,
        a_cards_for: float,
        a_cards_against: float,
        ref_strictness: float = 1.0,
        elo_diff: float = 0.0,
        is_cup: bool = False,
    ) -> tuple:
        """
        Empirical Bayes regressed cards expectation & Negative Binomial overdispersed probabilities.
        Baseline from 5,521 matches: Home 2.10, Away 2.39 (Total 4.49), Overdispersion phi=1.80.
        Returns: (exp_total_cards, prob_o35, prob_u35, prob_o45, prob_u45)
        """
        # 1. Regress noisy rolling 5-game sample towards historical league baselines
        h_shrunk = 0.35 * (h_cards_for or 2.10) + 0.65 * 2.10
        a_shrunk = 0.35 * (a_cards_for or 2.39) + 0.65 * 2.39
        base_cards = (h_shrunk + a_shrunk)

        # 2. Referee Strictness & Match Tension Factor
        tension_factor = 1.0 + max(0.0, 0.10 - abs(elo_diff / 400.0) * 0.05)
        cup_factor = 1.05 if is_cup else 1.00
        ref_factor = float(np.clip(ref_strictness or 1.0, 0.85, 1.25))

        exp_total = float(np.clip(base_cards * ref_factor * tension_factor * cup_factor, 2.8, 5.8))

        # 3. Negative Binomial distribution for overdispersion (phi=1.80)
        phi = 1.80
        p = 1.0 / phi
        n = exp_total * p / (1.0 - p)
        p_o35 = float(np.clip(1.0 - nbinom.cdf(3, n, p), 0.25, 0.75))
        p_u35 = float(1.0 - p_o35)
        p_o45 = float(np.clip(1.0 - nbinom.cdf(4, n, p), 0.15, 0.62))
        p_u45 = float(1.0 - p_o45)

        return round(exp_total, 1), round(p_o35, 3), round(p_u35, 3), round(p_o45, 3), round(p_u45, 3)

    @staticmethod
    def generate_goal_lines(score_mat: Any, exp_goals: float, lines: Optional[List[float]] = None) -> tuple[List[Dict[str, Any]], float]:
        """
        Compute Over/Under probabilities and fair odds across multiple goal lines.
        Returns: (lines_list, primary_line)
        """
        if lines is None:
            lines = [0.5, 1.5, 2.5, 3.5, 4.5, 5.5]

        score_arr = np.asarray(score_mat)
        # Primary line is closest half-goal line to expected total goals
        primary_line = min(lines, key=lambda l: abs(l - exp_goals))
        res = []
        for l in lines:
            p_o = float(sum(score_arr[i, j] for i in range(score_arr.shape[0]) for j in range(score_arr.shape[1]) if (i + j) > l))
            p_o = float(np.clip(p_o, 0.01, 0.99))
            p_u = float(1.0 - p_o)
            res.append({
                "line": float(l),
                "prob_over": round(p_o, 3),
                "prob_under": round(p_u, 3),
                "fair_odds_over": round(1.0 / max(0.01, p_o), 2),
                "fair_odds_under": round(1.0 / max(0.01, p_u), 2),
                "is_primary": bool(l == primary_line),
            })
        return res, primary_line

    @staticmethod
    def generate_corner_lines(exp_corners: float, lines: Optional[List[float]] = None) -> tuple[List[Dict[str, Any]], float]:
        """
        Compute Over/Under probabilities and fair odds across multiple corner lines
        using calibrated Negative Binomial distribution (phi=1.20).
        Returns: (lines_list, primary_line)
        """
        if lines is None:
            lines = [7.5, 8.5, 9.5, 10.5, 11.5, 12.5]

        primary_line = min(lines, key=lambda l: abs(l - exp_corners))
        phi = 1.20
        p = 1.0 / phi
        n = exp_corners * p / (1.0 - p)

        res = []
        for l in lines:
            k = int(l)
            p_o = float(np.clip(1.0 - nbinom.cdf(k, n, p), 0.02, 0.98))
            p_u = float(1.0 - p_o)
            res.append({
                "line": float(l),
                "prob_over": round(p_o, 3),
                "prob_under": round(p_u, 3),
                "fair_odds_over": round(1.0 / max(0.01, p_o), 2),
                "fair_odds_under": round(1.0 / max(0.01, p_u), 2),
                "is_primary": bool(l == primary_line),
            })
        return res, primary_line

    @staticmethod
    def generate_card_lines(exp_cards: float, lines: Optional[List[float]] = None) -> tuple[List[Dict[str, Any]], float]:
        """
        Compute Over/Under probabilities and fair odds across multiple card lines
        using calibrated Negative Binomial distribution (phi=1.80).
        Returns: (lines_list, primary_line)
        """
        if lines is None:
            lines = [1.5, 2.5, 3.5, 4.5, 5.5, 6.5]

        primary_line = min(lines, key=lambda l: abs(l - exp_cards))
        phi = 1.80
        p = 1.0 / phi
        n = exp_cards * p / (1.0 - p)

        res = []
        for l in lines:
            k = int(l)
            p_o = float(np.clip(1.0 - nbinom.cdf(k, n, p), 0.02, 0.98))
            p_u = float(1.0 - p_o)
            res.append({
                "line": float(l),
                "prob_over": round(p_o, 3),
                "prob_under": round(p_u, 3),
                "fair_odds_over": round(1.0 / max(0.01, p_o), 2),
                "fair_odds_under": round(1.0 / max(0.01, p_u), 2),
                "is_primary": bool(l == primary_line),
            })
        return res, primary_line

    def predict_match(
        self,
        league_key: str,
        home_team: str,
        away_team: str,
        referee: Optional[str] = None,
        odds_home: Optional[float] = None,
        odds_draw: Optional[float] = None,
        odds_away: Optional[float] = None,
        odds_over25: Optional[float] = None,
        odds_under25: Optional[float] = None,
        odds_btts_yes: Optional[float] = None,
        odds_btts_no: Optional[float] = None,
        odds_corners_over95: Optional[float] = None,
        odds_corners_under95: Optional[float] = None,
        odds_cards_over35: Optional[float] = None,
        odds_cards_under35: Optional[float] = None,
        match_date: Optional[pd.Timestamp] = None,
        is_neutral: Optional[bool] = None,
        tournament: Optional[str] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Generate comprehensive match predictions across 1X2, Goals, BTTS, Corners, and Cards (Domestic, International & European Cups)."""
        home_norm = normalize_team_name(home_team)
        away_norm = normalize_team_name(away_team)

        is_intl = bool(LEAGUES.get(league_key, {}).get("is_international") or league_key == "International")
        is_cup = LEAGUES.get(league_key, {}).get("is_cup", False)
        bundle = self.bundles.get(league_key)

        # 1. International Match Prediction (Calibrated LightGBM + Elo Bivariate Poisson)
        if is_intl and ("International" in self.bundles):
            intl_bundle = self.bundles["International"]
            models = intl_bundle["models"]
            pipeline = intl_bundle["pipeline"]

            tourn_name = tournament or LEAGUES.get(league_key, {}).get("name") or league_key
            eff_neutral = bool(is_neutral if is_neutral is not None else kwargs.get("neutral", False))

            home_norm = pipeline.elo_engine.resolve_team(home_team) if hasattr(pipeline, "elo_engine") else normalize_team_name(home_team)
            away_norm = pipeline.elo_engine.resolve_team(away_team) if hasattr(pipeline, "elo_engine") else normalize_team_name(away_team)

            X_infer = pipeline.build_inference_features(
                home_team=home_norm,
                away_team=away_norm,
                date=match_date,
                is_neutral=eff_neutral,
                tournament=tourn_name,
            )

            probs_1x2_ml = models["model_1x2"].predict_proba(X_infer)[0]
            prob_over25_ml = float(models["model_over25"].predict_proba(X_infer)[0][1])
            prob_btts_ml = float(models["model_btts"].predict_proba(X_infer)[0][1])

            # Elo-based bivariate Poisson generator
            home_elo = float(pipeline.elo_engine.get_rating(home_norm)) if hasattr(pipeline, "elo_engine") else 1500.0
            away_elo = float(pipeline.elo_engine.get_rating(away_norm)) if hasattr(pipeline, "elo_engine") else 1500.0
            adv = 0.0 if eff_neutral else 65.0
            elo_diff_val = (home_elo + adv) - away_elo

            home_adv_rate = 0.20 if not eff_neutral else 0.0
            elo_xg_adj = (elo_diff_val / 400.0) * 0.35
            h_xg = max(0.35, min(3.8, float(np.exp(home_adv_rate + elo_xg_adj * 0.5))))
            a_xg = max(0.25, min(3.5, float(np.exp(-elo_xg_adj * 0.5))))

            score_mat = np.zeros((8, 8))
            for h_g in range(8):
                for a_g in range(8):
                    score_mat[h_g, a_g] = poisson.pmf(h_g, h_xg) * poisson.pmf(a_g, a_xg)

            rho = -0.04
            score_mat[0, 0] *= max(0.01, 1.0 - h_xg * a_xg * rho)
            score_mat[0, 1] *= max(0.01, 1.0 + h_xg * rho)
            score_mat[1, 0] *= max(0.01, 1.0 + a_xg * rho)
            score_mat[1, 1] *= max(0.01, 1.0 - rho)
            score_mat /= np.sum(score_mat)

            p_home_pois = float(np.sum(np.tril(score_mat, -1)))
            p_draw_pois = float(np.sum(np.diag(score_mat)))
            p_away_pois = float(np.sum(np.triu(score_mat, 1)))
            sum_pois = p_home_pois + p_draw_pois + p_away_pois
            if sum_pois > 0:
                p_home_pois, p_draw_pois, p_away_pois = p_home_pois / sum_pois, p_draw_pois / sum_pois, p_away_pois / sum_pois

            p_over25_pois = float(np.sum([score_mat[h, a] for h in range(8) for a in range(8) if h + a > 2.5]))
            p_btts_pois = float(np.sum(score_mat[1:, 1:]))

            p_home = float(0.70 * probs_1x2_ml[0] + 0.30 * p_home_pois)
            p_draw = float(0.70 * probs_1x2_ml[1] + 0.30 * p_draw_pois)
            p_away = float(0.70 * probs_1x2_ml[2] + 0.30 * p_away_pois)
            sum_1x2 = p_home + p_draw + p_away
            p_home, p_draw, p_away = p_home / sum_1x2, p_draw / sum_1x2, p_away / sum_1x2

            p_over25 = float(0.65 * prob_over25_ml + 0.35 * p_over25_pois)
            p_under25 = float(1.0 - p_over25)

            p_btts_yes = float(0.65 * prob_btts_ml + 0.35 * p_btts_pois)
            p_btts_no = float(1.0 - p_btts_yes)

            max_idx = np.unravel_index(np.argmax(score_mat), score_mat.shape)
            most_likely_score = f"{max_idx[0]}-{max_idx[1]}"
            most_likely_score_prob = float(score_mat[max_idx])

            # Corners and Cards calibration
            exp_corners, p_corners_o95, p_corners_u95, p_corners_o105 = self.calibrate_corners_expectancy(
                h_corn_for=5.5,
                h_corn_against=4.5,
                a_corn_for=4.5,
                a_corn_against=5.5,
                elo_diff=elo_diff_val,
            )

            exp_cards, p_cards_o35, p_cards_u35, p_cards_o45, p_cards_u45 = self.calibrate_cards_expectancy(
                h_cards_for=2.1,
                h_cards_against=2.4,
                a_cards_for=2.4,
                a_cards_against=2.1,
                ref_strictness=1.0,
                elo_diff=elo_diff_val,
                is_cup=True,
            )

            ref_profile = {
                "referee_name": referee or "FIFA Official",
                "strictness_index": 1.0,
                "strictness_label": "International Official",
                "avg_cards": 4.2,
                "avg_fouls": 24.5,
            }

        # 2. Domestic League Match Prediction (Full Multi-Model Stack)
        elif bundle and not is_cup:
            models = bundle["models"]
            pipeline = bundle["pipeline"]

            X_infer = pipeline.build_inference_features(
                home_team=home_norm,
                away_team=away_norm,
                match_date=match_date,
                referee=referee,
                odds_home=odds_home,
                odds_draw=odds_draw,
                odds_away=odds_away,
            )

            probs_1x2_ml = models["model_1x2"].predict_proba(X_infer)[0]
            prob_over25_ml = float(models["model_over25"].predict_proba(X_infer)[0][1])
            prob_btts_ml = float(models["model_btts"].predict_proba(X_infer)[0][1])

            dc_preds = pipeline.dixon_coles_engine.predict_match_probabilities(home_norm, away_norm)
            probs_1x2_dc = np.array([dc_preds["prob_home"], dc_preds["prob_draw"], dc_preds["prob_away"]])
            prob_over25_dc = dc_preds["prob_over25"]
            prob_btts_dc = dc_preds["prob_btts_yes"]

            p_home = float(0.70 * probs_1x2_ml[0] + 0.30 * probs_1x2_dc[0])
            p_draw = float(0.70 * probs_1x2_ml[1] + 0.30 * probs_1x2_dc[1])
            p_away = float(0.70 * probs_1x2_ml[2] + 0.30 * probs_1x2_dc[2])
            sum_1x2 = p_home + p_draw + p_away
            p_home, p_draw, p_away = p_home / sum_1x2, p_draw / sum_1x2, p_away / sum_1x2

            p_over25 = float(0.65 * prob_over25_ml + 0.35 * prob_over25_dc)
            p_under25 = float(1.0 - p_over25)

            p_btts_yes = float(0.65 * prob_btts_ml + 0.35 * prob_btts_dc)
            p_btts_no = float(1.0 - p_btts_yes)

            home_elo = float(pipeline.elo_engine.get_rating(home_norm)) if pipeline and hasattr(pipeline, "elo_engine") else 1500.0
            away_elo = float(pipeline.elo_engine.get_rating(away_norm)) if pipeline and hasattr(pipeline, "elo_engine") else 1500.0
            elo_diff_val = home_elo - away_elo

            # Calibrated Corners (Empirical Bayes + Negative Binomial)
            eff_date = match_date if match_date is not None else pd.Timestamp.now()
            h_form_5 = pipeline.form_tracker.get_team_rolling_features(home_norm, eff_date, n_matches=5) if hasattr(pipeline, "form_tracker") else {}
            a_form_5 = pipeline.form_tracker.get_team_rolling_features(away_norm, eff_date, n_matches=5) if hasattr(pipeline, "form_tracker") else {}
            
            exp_corners, p_corners_o95, p_corners_u95, p_corners_o105 = self.calibrate_corners_expectancy(
                h_corn_for=h_form_5.get("corners_for_last5", 5.5),
                h_corn_against=h_form_5.get("corners_against_last5", 4.5),
                a_corn_for=a_form_5.get("corners_for_last5", 4.5),
                a_corn_against=a_form_5.get("corners_against_last5", 5.5),
                elo_diff=elo_diff_val,
            )

            # Calibrated Cards (Referee Scaling + Negative Binomial)
            ref_profile = pipeline.referee_engine.get_referee_profile(referee, match_date) if hasattr(pipeline, "referee_engine") else {"strictness_index": 1.0, "avg_cards": 4.2}
            ref_strict = float(ref_profile.get("strictness_index", 1.0))
            
            exp_cards, p_cards_o35, p_cards_u35, p_cards_o45, p_cards_u45 = self.calibrate_cards_expectancy(
                h_cards_for=h_form_5.get("cards_for_last5", 2.1),
                h_cards_against=h_form_5.get("cards_against_last5", 2.4),
                a_cards_for=a_form_5.get("cards_for_last5", 2.4),
                a_cards_against=a_form_5.get("cards_against_last5", 2.1),
                ref_strictness=ref_strict,
                elo_diff=elo_diff_val,
                is_cup=False,
            )
            h_xg = float(dc_preds["lambda_home"])
            a_xg = float(dc_preds["mu_away"])
            score_mat = dc_preds["score_matrix"]
            most_likely_score = dc_preds["most_likely_score"]
            most_likely_score_prob = float(dc_preds["most_likely_score_prob"])

        # 2. European Cup / Cross-League Match Prediction
        else:
            h_prof = self._find_team_profile(home_norm)
            a_prof = self._find_team_profile(away_norm)

            home_elo = float(h_prof["elo"])
            away_elo = float(a_prof["elo"])

            # Cross-League Dixon-Coles expectancy with Elo calibration
            home_adv = 0.20
            elo_diff = home_elo - away_elo
            elo_xg_adj = (elo_diff / 400.0) * 0.35
            h_xg = float(np.exp(home_adv + h_prof["attack"] - a_prof["defense"] + elo_xg_adj * 0.5))
            a_xg = float(np.exp(a_prof["attack"] - h_prof["defense"] - elo_xg_adj * 0.5))
            h_xg = max(0.35, min(3.8, h_xg))
            a_xg = max(0.25, min(3.5, a_xg))

            # Joint bivariate Poisson score matrix
            score_mat = np.zeros((8, 8))
            for h_g in range(8):
                for a_g in range(8):
                    score_mat[h_g][a_g] = poisson.pmf(h_g, h_xg) * poisson.pmf(a_g, a_xg)

            # Dixon-Coles tau adjustment for 0-0, 1-0, 0-1, 1-1
            rho = -0.04
            score_mat[0, 0] *= max(0.01, 1.0 - h_xg * a_xg * rho)
            score_mat[0, 1] *= max(0.01, 1.0 + h_xg * rho)
            score_mat[1, 0] *= max(0.01, 1.0 + a_xg * rho)
            score_mat[1, 1] *= max(0.01, 1.0 - rho)
            score_mat = score_mat / np.sum(score_mat)

            p_home = float(np.sum(np.tril(score_mat, -1)))
            p_draw = float(np.sum(np.diag(score_mat)))
            p_away = float(np.sum(np.triu(score_mat, 1)))
            sum_p = p_home + p_draw + p_away
            if sum_p > 0:
                p_home, p_draw, p_away = p_home / sum_p, p_draw / sum_p, p_away / sum_p

            # Over / Under 2.5 & BTTS
            p_over25 = float(sum(score_mat[i, j] for i in range(8) for j in range(8) if i + j > 2.5))
            p_under25 = float(1.0 - p_over25)
            p_btts_yes = float(sum(score_mat[i, j] for i in range(1, 8) for j in range(1, 8)))
            p_btts_no = float(1.0 - p_btts_yes)

            max_idx = np.unravel_index(np.argmax(score_mat), score_mat.shape)
            most_likely_score = f"{max_idx[0]}-{max_idx[1]}"
            most_likely_score_prob = float(score_mat[max_idx])

            # Calibrated Corners (European Cups: Empirical Bayes + Negative Binomial)
            h_form = h_prof.get("form") or {}
            a_form = a_prof.get("form") or {}
            h_corn_for = h_form.get("corners_for_last5", 5.5) if isinstance(h_form, dict) else 5.5
            h_corn_ag = h_form.get("corners_against_last5", 4.5) if isinstance(h_form, dict) else 4.5
            a_corn_for = a_form.get("corners_for_last5", 4.5) if isinstance(a_form, dict) else 4.5
            a_corn_ag = a_form.get("corners_against_last5", 5.5) if isinstance(a_form, dict) else 5.5

            exp_corners, p_corners_o95, p_corners_u95, p_corners_o105 = self.calibrate_corners_expectancy(
                h_corn_for=h_corn_for,
                h_corn_against=h_corn_ag,
                a_corn_for=a_corn_for,
                a_corn_against=a_corn_ag,
                elo_diff=elo_diff,
            )

            # Calibrated Cards (European Cups: Ref Scaling + Negative Binomial)
            h_cards = h_form.get("cards_for_last5", 2.1) if isinstance(h_form, dict) else 2.1
            a_cards = a_form.get("cards_for_last5", 2.4) if isinstance(a_form, dict) else 2.4

            exp_cards, p_cards_o35, p_cards_u35, p_cards_o45, p_cards_u45 = self.calibrate_cards_expectancy(
                h_cards_for=h_cards,
                h_cards_against=2.4,
                a_cards_for=a_cards,
                a_cards_against=2.1,
                ref_strictness=1.05,
                elo_diff=elo_diff,
                is_cup=True,
            )

            ref_profile = {
                "referee_name": referee or "UEFA Official",
                "strictness_index": 1.05,
                "strictness_label": "UEFA European Cup",
                "avg_cards": 4.5,
                "avg_fouls": 25.0,
            }

        # 3. Fair Odds
        fair_odds_home = round(1.0 / max(0.01, p_home), 2)
        fair_odds_draw = round(1.0 / max(0.01, p_draw), 2)
        fair_odds_away = round(1.0 / max(0.01, p_away), 2)
        fair_odds_o25 = round(1.0 / max(0.01, p_over25), 2)
        fair_odds_u25 = round(1.0 / max(0.01, p_under25), 2)
        fair_odds_btts_y = round(1.0 / max(0.01, p_btts_yes), 2)
        fair_odds_btts_n = round(1.0 / max(0.01, p_btts_no), 2)
        fair_odds_corn_o95 = round(1.0 / max(0.01, p_corners_o95), 2)
        fair_odds_corn_u95 = round(1.0 / max(0.01, p_corners_u95), 2)
        fair_odds_card_o35 = round(1.0 / max(0.01, p_cards_o35), 2)
        fair_odds_card_u35 = round(1.0 / max(0.01, p_cards_u35), 2)

        # 4. Betting Analysis & EV Across All Markets
        betting_insights = []
        candidates = []

        all_market_selections = [
            # 1X2
            ("1X2", "Home Win", p_home, odds_home, fair_odds_home),
            ("1X2", "Draw", p_draw, odds_draw, fair_odds_draw),
            ("1X2", "Away Win", p_away, odds_away, fair_odds_away),
            # Goals
            ("Goals", "Over 2.5 Goals", p_over25, odds_over25, fair_odds_o25),
            ("Goals", "Under 2.5 Goals", p_under25, odds_under25, fair_odds_u25),
            # BTTS
            ("BTTS", "BTTS Yes", p_btts_yes, odds_btts_yes, fair_odds_btts_y),
            ("BTTS", "BTTS No", p_btts_no, odds_btts_no, fair_odds_btts_n),
            # Corners
            ("Corners", "Over 9.5 Corners", p_corners_o95, odds_corners_over95, fair_odds_corn_o95),
            ("Corners", "Under 9.5 Corners", p_corners_u95, odds_corners_under95, fair_odds_corn_u95),
            # Cards
            ("Cards", "Over 3.5 Cards", p_cards_o35, odds_cards_over35, fair_odds_card_o35),
            ("Cards", "Under 3.5 Cards", p_cards_u35, odds_cards_under35, fair_odds_card_u35),
        ]

        for mkt, sel, p_sel, o_sel, f_sel in all_market_selections:
            has_odds = bool(o_sel and o_sel > 1.0 and p_sel and p_sel > 0)
            ev = calculate_ev(p_sel, o_sel) if has_odds else None
            kelly = calculate_kelly_stake(p_sel, o_sel, fraction=DEFAULT_KELLY_FRACTION) if has_odds else None

            betting_insights.append({
                "market": mkt,
                "selection": sel,
                "odds": o_sel if has_odds else None,
                "model_prob": p_sel,
                "fair_odds": f_sel,
                "ev": ev,
                "kelly": kelly
            })

            # Bounded Value Bet Qualification:
            # 1. Valid market odds and positive probability
            # 2. Odds within realistic bounds (<= MAX_VALUE_ODDS, e.g. 3.20)
            # 3. Model probability >= MIN_VALUE_PROB (e.g. 30%)
            # 4. EV >= MIN_VALUE_THRESHOLD (e.g. +3.0%)
            if (has_odds and ev is not None and ev >= MIN_VALUE_THRESHOLD
                    and o_sel <= MAX_VALUE_ODDS and p_sel >= MIN_VALUE_PROB):
                candidates.append({
                    "market": mkt,
                    "selection": sel,
                    "odds": o_sel,
                    "prob": p_sel,
                    "ev": ev,
                    "kelly": kelly or 0.0
                })

        if candidates:
            # Rank candidates primarily by risk-adjusted Quarter-Kelly stake, tie-break by EV
            candidates.sort(key=lambda c: (c["kelly"], c["ev"]), reverse=True)
            best_pick = candidates[0]
            max_ev = best_pick["ev"]
        else:
            max_ev = -1.0
            highest_prob = max(p_home, p_draw, p_away)
            if highest_prob == p_home:
                best_pick = {"market": "1X2", "selection": f"{home_norm} (Fav)", "odds": odds_home, "prob": p_home, "ev": 0.0, "kelly": 0.0}
            elif highest_prob == p_away:
                best_pick = {"market": "1X2", "selection": f"{away_norm} (Fav)", "odds": odds_away, "prob": p_away, "ev": 0.0, "kelly": 0.0}
            else:
                best_pick = {"market": "1X2", "selection": "Draw", "odds": odds_draw, "prob": p_draw, "ev": 0.0, "kelly": 0.0}

        goal_lines, primary_goal_line = self.generate_goal_lines(score_mat, float(h_xg + a_xg))
        corner_lines, primary_corner_line = self.generate_corner_lines(exp_corners)
        card_lines, primary_card_line = self.generate_card_lines(exp_cards)

        return {
            "league_key": league_key,
            "home_team": home_norm,
            "away_team": away_norm,
            "referee": ref_profile,
            "home_elo": home_elo,
            "away_elo": away_elo,
            "expected_goals_home": h_xg,
            "expected_goals_away": a_xg,
            "expected_total_goals": float(h_xg + a_xg),
            "primary_goal_line": primary_goal_line,
            "primary_corner_line": primary_corner_line,
            "primary_card_line": primary_card_line,
            "goal_lines": goal_lines,
            "corner_lines": corner_lines,
            "card_lines": card_lines,

            # Probabilities & Fair Odds
            "prob_home": float(p_home),
            "prob_draw": float(p_draw),
            "prob_away": float(p_away),
            "fair_odds_home": fair_odds_home,
            "fair_odds_draw": fair_odds_draw,
            "fair_odds_away": fair_odds_away,

            "prob_over25": float(p_over25),
            "prob_under25": float(p_under25),
            "fair_odds_over25": fair_odds_o25,
            "fair_odds_under25": fair_odds_u25,

            "prob_btts_yes": float(p_btts_yes),
            "prob_btts": float(p_btts_yes),
            "prob_btts_no": float(p_btts_no),
            "fair_odds_btts_yes": fair_odds_btts_y,
            "fair_odds_btts_no": fair_odds_btts_n,

            "most_likely_score": most_likely_score,
            "most_likely_score_prob": most_likely_score_prob,
            "score_matrix": score_mat.tolist() if hasattr(score_mat, "tolist") else score_mat,

            # Corners Projections & Fair Odds
            "expected_corners": round(exp_corners, 1),
            "prob_corners_over95": float(p_corners_o95),
            "prob_corners_under95": float(p_corners_u95),
            "fair_odds_corners_over95": fair_odds_corn_o95,
            "fair_odds_corners_under95": fair_odds_corn_u95,
            "prob_corners_over105": float(p_corners_o105),

            # Cards & Referee Projections & Fair Odds
            "expected_cards": round(exp_cards, 1),
            "prob_cards_over35": float(p_cards_o35),
            "prob_cards_under35": float(p_cards_u35),
            "fair_odds_cards_over35": fair_odds_card_o35,
            "fair_odds_cards_under35": fair_odds_card_u35,
            "prob_cards_over45": float(p_cards_o45),
            "prob_cards_under45": float(p_cards_u45),

            # Market Odds passed in
            "odds_home": odds_home,
            "odds_draw": odds_draw,
            "odds_away": odds_away,
            "odds_over25": odds_over25,
            "odds_under25": odds_under25,
            "odds_btts_yes": odds_btts_yes,
            "odds_btts_no": odds_btts_no,
            "odds_corners_over95": odds_corners_over95,
            "odds_corners_under95": odds_corners_under95,
            "odds_cards_over35": odds_cards_over35,
            "odds_cards_under35": odds_cards_under35,

            "best_pick": best_pick,
            "has_value": bool(max_ev >= MIN_VALUE_THRESHOLD),
            "betting_insights": betting_insights,
        }
