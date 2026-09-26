"""Milestone 1 Adversarial Test Suite - Challenger 2.

Empirical verification of:
1. Config integrity: 22 competitions, expected keys, types, values, uniqueness, and synchronization.
2. Bypassing domestic downloaders: fetcher.py and auto_update.py skip all is_cup=True competitions.
3. Team name normalization: 50+ national team variations against normalize_team_name and teams_match,
   including edge cases, symmetry, reflexivity, and collision discrimination.
4. Adversarial vulnerability probes: proving case-sensitivity gaps, missing standalone aliases,
   and catastrophic false-positive collisions across distinct sovereign nations.
"""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

# Ensure project root and Football are in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FOOTBALL_DIR = PROJECT_ROOT / "Football"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(FOOTBALL_DIR) not in sys.path:
    sys.path.insert(0, str(FOOTBALL_DIR))

from football_core.config import LEAGUES, SEASONS
from football_core.data.espn_client import ESPN_LEAGUE_CODES
from football_core.data import fetcher, auto_update
from football_core.utils.helpers import (
    normalize_team_name,
    teams_match,
    strip_accents,
    NATIONAL_TEAM_MAP,
    NATIONAL_TEAM_ALIASES,
)


class TestConfigIntegrity(unittest.TestCase):
    """Area 1: Config integrity verification across all competitions."""

    EXPECTED_KEYS = {
        "name",
        "country",
        "code",
        "espn_code",
        "flag",
        "is_cup",
        "is_international",
    }

    DOMESTIC_LEAGUES = {
        "EPL",
        "LaLiga",
        "SerieA",
        "Bundesliga",
        "Ligue1",
        "Belgium",
        "Eredivisie",
        "PrimeiraLiga",
        "ScottishPrem",
    }

    EUROPEAN_CUPS = {"UCL", "UEL", "UECL"}

    INTERNATIONAL_COMPETITIONS = {
        "NationsLeague",
        "WorldCup",
        "WCQ_UEFA",
        "WCQ_CONMEBOL",
        "WCQ_CAF",
        "Euro",
        "CopaAmerica",
        "AFCON",
        "Friendlies",
        "GoldCup",
    }

    EXPECTED_ESPN_CODES = {
        "EPL": "eng.1",
        "LaLiga": "esp.1",
        "SerieA": "ita.1",
        "Bundesliga": "ger.1",
        "Ligue1": "fra.1",
        "Belgium": "bel.1",
        "Eredivisie": "ned.1",
        "PrimeiraLiga": "por.1",
        "ScottishPrem": "sco.1",
        "UCL": "uefa.champions",
        "UEL": "uefa.europa",
        "UECL": "uefa.europa.conf",
        "NationsLeague": "uefa.nations",
        "WorldCup": "fifa.world",
        "WCQ_UEFA": "fifa.worldq.uefa",
        "WCQ_CONMEBOL": "fifa.worldq.conmebol",
        "WCQ_CAF": "fifa.worldq.caf",
        "Euro": "uefa.euro",
        "CopaAmerica": "conmebol.america",
        "AFCON": "caf.nations",
        "Friendlies": "fifa.friendly",
        "GoldCup": "concacaf.gold",
    }

    def test_total_competition_count_is_22(self):
        """Verify LEAGUES contains exactly 22 competitions."""
        self.assertEqual(
            len(LEAGUES),
            22,
            f"Expected exactly 22 competitions in LEAGUES, found {len(LEAGUES)}",
        )

    def test_competition_categories_membership(self):
        """Verify exact partition into 9 domestic, 3 European cups, and 10 international."""
        all_expected = (
            self.DOMESTIC_LEAGUES | self.EUROPEAN_CUPS | self.INTERNATIONAL_COMPETITIONS
        )
        self.assertEqual(
            set(LEAGUES.keys()),
            all_expected,
            f"LEAGUES keys mismatch: diff={set(LEAGUES.keys()) ^ all_expected}",
        )

    def test_all_competitions_have_required_keys(self):
        """Verify each of the 22 competitions has all 7 mandatory keys."""
        for league_key, conf in LEAGUES.items():
            for key in self.EXPECTED_KEYS:
                self.assertIn(
                    key,
                    conf,
                    f"Competition '{league_key}' is missing required key '{key}'",
                )

    def test_field_types_and_non_empty(self):
        """Verify strict types and non-empty values for required fields."""
        for league_key, conf in LEAGUES.items():
            self.assertIsInstance(
                conf["name"], str, f"{league_key} name must be str"
            )
            self.assertTrue(len(conf["name"].strip()) > 0, f"{league_key} name is empty")

            self.assertIsInstance(
                conf["country"], str, f"{league_key} country must be str"
            )
            self.assertTrue(
                len(conf["country"].strip()) > 0, f"{league_key} country is empty"
            )

            self.assertIsInstance(
                conf["code"], str, f"{league_key} code must be str"
            )
            self.assertTrue(len(conf["code"].strip()) > 0, f"{league_key} code is empty")

            self.assertIsInstance(
                conf["espn_code"], str, f"{league_key} espn_code must be str"
            )
            self.assertTrue(
                len(conf["espn_code"].strip()) > 0, f"{league_key} espn_code is empty"
            )

            self.assertIsInstance(
                conf["flag"], str, f"{league_key} flag must be str"
            )
            self.assertTrue(len(conf["flag"].strip()) > 0, f"{league_key} flag is empty")

            # Must be strictly bool (not int or str)
            self.assertIs(
                type(conf["is_cup"]),
                bool,
                f"{league_key} is_cup must be bool, got {type(conf['is_cup'])}",
            )
            self.assertIs(
                type(conf["is_international"]),
                bool,
                f"{league_key} is_international must be bool, got {type(conf['is_international'])}",
            )

    def test_is_cup_values(self):
        """Verify is_cup is True for cups and international, False for domestic."""
        for league_key in self.DOMESTIC_LEAGUES:
            self.assertFalse(
                LEAGUES[league_key]["is_cup"],
                f"Domestic league {league_key} must have is_cup == False",
            )
        for league_key in self.EUROPEAN_CUPS | self.INTERNATIONAL_COMPETITIONS:
            self.assertTrue(
                LEAGUES[league_key]["is_cup"],
                f"Cup/International {league_key} must have is_cup == True",
            )

    def test_is_international_values(self):
        """Verify is_international is True for international, False for domestic and club cups."""
        for league_key in self.DOMESTIC_LEAGUES | self.EUROPEAN_CUPS:
            self.assertFalse(
                LEAGUES[league_key]["is_international"],
                f"Club competition {league_key} must have is_international == False",
            )
        for league_key in self.INTERNATIONAL_COMPETITIONS:
            self.assertTrue(
                LEAGUES[league_key]["is_international"],
                f"International competition {league_key} must have is_international == True",
            )

    def test_odds_key_values(self):
        """Verify odds_key is None for international and non-empty str for club comps."""
        for league_key in self.INTERNATIONAL_COMPETITIONS:
            self.assertIsNone(
                LEAGUES[league_key].get("odds_key"),
                f"International comp {league_key} must have odds_key == None",
            )
        for league_key in self.DOMESTIC_LEAGUES | self.EUROPEAN_CUPS:
            self.assertIsInstance(
                LEAGUES[league_key].get("odds_key"),
                str,
                f"Club comp {league_key} must have non-empty string odds_key",
            )

    def test_espn_code_synchronization_and_uniqueness(self):
        """Verify espn_code values match expected values and ESPN_LEAGUE_CODES dictionary."""
        # 1. Match expected mapping
        for league_key, expected_espn in self.EXPECTED_ESPN_CODES.items():
            self.assertEqual(
                LEAGUES[league_key]["espn_code"],
                expected_espn,
                f"LEAGUES[{league_key}]['espn_code'] expected {expected_espn}, got {LEAGUES[league_key]['espn_code']}",
            )
            self.assertEqual(
                ESPN_LEAGUE_CODES.get(league_key),
                expected_espn,
                f"ESPN_LEAGUE_CODES[{league_key}] expected {expected_espn}, got {ESPN_LEAGUE_CODES.get(league_key)}",
            )

        # 2. Uniqueness of espn_code across all 22 competitions
        all_espn_codes = [c["espn_code"] for c in LEAGUES.values()]
        self.assertEqual(
            len(all_espn_codes),
            len(set(all_espn_codes)),
            f"Duplicate espn_code found: {all_espn_codes}",
        )

        # 3. Uniqueness of division/tournament codes
        all_codes = [c["code"] for c in LEAGUES.values()]
        self.assertEqual(
            len(all_codes),
            len(set(all_codes)),
            f"Duplicate code found: {all_codes}",
        )


class TestDownloaderBypass(unittest.TestCase):
    """Area 2: Verify fetcher.py and auto_update.py skip competitions where is_cup is True."""

    @patch("football_core.data.fetcher.download_league_season")
    def test_fetch_all_data_skips_all_cups_and_international(self, mock_download):
        """fetch_all_data must iterate ONLY over 9 domestic leagues and 0 cups/international."""
        mock_download.return_value = None

        result = fetcher.fetch_all_data(force=False)
        called_leagues = {call.args[0] for call in mock_download.call_args_list}

        # 1. All 13 is_cup=True competitions must NEVER be called
        for league_key, info in LEAGUES.items():
            if info.get("is_cup"):
                self.assertNotIn(
                    league_key,
                    called_leagues,
                    f"CRITICAL: fetch_all_data attempted download for cup/international: {league_key}",
                )

        # 2. All 9 domestic leagues MUST be called
        expected_domestic = {
            "EPL",
            "LaLiga",
            "SerieA",
            "Bundesliga",
            "Ligue1",
            "Belgium",
            "Eredivisie",
            "PrimeiraLiga",
            "ScottishPrem",
        }
        self.assertEqual(
            called_leagues,
            expected_domestic,
            f"fetch_all_data called unexpected leagues: {called_leagues ^ expected_domestic}",
        )

    @patch("football_core.data.fetcher.download_league_season")
    def test_update_active_seasons_skips_all_cups_and_international(
        self, mock_download
    ):
        """update_active_seasons must iterate ONLY over 9 domestic leagues."""
        mock_download.return_value = None

        result = fetcher.update_active_seasons(["2526", "2627"])
        called_leagues = {call.args[0] for call in mock_download.call_args_list}

        for league_key, info in LEAGUES.items():
            if info.get("is_cup"):
                self.assertNotIn(
                    league_key,
                    called_leagues,
                    f"CRITICAL: update_active_seasons attempted download for cup/international: {league_key}",
                )

        expected_domestic = {
            "EPL",
            "LaLiga",
            "SerieA",
            "Bundesliga",
            "Ligue1",
            "Belgium",
            "Eredivisie",
            "PrimeiraLiga",
            "ScottishPrem",
        }
        self.assertEqual(called_leagues, expected_domestic)

    @patch("football_core.data.auto_update.save_processed_data")
    @patch("football_core.data.auto_update.clean_match_data")
    @patch("football_core.data.auto_update.load_raw_league_data")
    @patch("football_core.data.auto_update.download_league_season")
    def test_check_and_auto_update_skips_all_cups_and_international(
        self, mock_download, mock_load, mock_clean, mock_save
    ):
        """check_and_auto_update must process ONLY domestic leagues, bypassing is_cup=True."""
        mock_download.return_value = None
        mock_load.return_value = MagicMock(empty=True)

        res = auto_update.check_and_auto_update(force=True)
        called_leagues = {call.args[0] for call in mock_download.call_args_list}

        for league_key, info in LEAGUES.items():
            if info.get("is_cup"):
                self.assertNotIn(
                    league_key,
                    called_leagues,
                    f"CRITICAL: auto_update attempted download for cup/international: {league_key}",
                )

        expected_domestic = {
            "EPL",
            "LaLiga",
            "SerieA",
            "Bundesliga",
            "Ligue1",
            "Belgium",
            "Eredivisie",
            "PrimeiraLiga",
            "ScottishPrem",
        }
        self.assertEqual(called_leagues, expected_domestic)

    def test_direct_download_on_cup_fails_gracefully_without_crash(self):
        """Even if download_league_season is called directly with a cup, it must return None without raising."""
        res = fetcher.download_league_season("WorldCup", "9999", force=False)
        self.assertIsNone(
            res, "download_league_season with invalid/cup season should return None"
        )


class TestTeamNameNormalization(unittest.TestCase):
    """Area 3: Test 50+ national team variations against normalize_team_name and teams_match."""

    # 55+ national team variations across all FIFA confederations
    VARIATION_PAIRS = [
        # USA variations (Canonical in results.csv: "United States")
        ("USA", "United States"),
        ("United States of America", "United States"),
        ("U.S.A.", "United States"),
        ("United States", "United States"),
        # Ivory Coast variations (Canonical: "Ivory Coast")
        ("Côte d'Ivoire", "Ivory Coast"),
        ("Cote d'Ivoire", "Ivory Coast"),
        ("Ivory Coast", "Ivory Coast"),
        # Turkey variations (Canonical: "Turkey")
        ("Türkiye", "Turkey"),
        ("Turkiye", "Turkey"),
        ("Turkey", "Turkey"),
        # Czech Republic variations (Canonical: "Czech Republic")
        ("Czechia", "Czech Republic"),
        ("Czech Republic", "Czech Republic"),
        # Bosnia variations (Canonical: "Bosnia and Herzegovina")
        ("Bosnia-Herzegovina", "Bosnia and Herzegovina"),
        ("Bosnia and Herzegovina", "Bosnia and Herzegovina"),
        ("Bosnia", "Bosnia and Herzegovina"),
        # South Korea variations (Canonical: "South Korea")
        ("Korea Republic", "South Korea"),
        ("South Korea", "South Korea"),
        # Iran variations (Canonical: "Iran")
        ("IR Iran", "Iran"),
        ("Iran", "Iran"),
        # DR Congo variations (Canonical: "DR Congo")
        ("Congo DR", "DR Congo"),
        ("Democratic Republic of the Congo", "DR Congo"),
        ("DR Congo", "DR Congo"),
        # Cape Verde variations (Canonical: "Cape Verde")
        ("Cabo Verde", "Cape Verde"),
        ("Cape Verde", "Cape Verde"),
        # Ireland variations (Canonical: "Republic of Ireland")
        ("Ireland", "Republic of Ireland"),
        ("Republic of Ireland", "Republic of Ireland"),
        # North Macedonia variations (Canonical: "North Macedonia")
        ("FYR Macedonia", "North Macedonia"),
        ("North Macedonia", "North Macedonia"),
        # Trinidad and Tobago variations (Canonical: "Trinidad and Tobago")
        ("Trinidad & Tobago", "Trinidad and Tobago"),
        ("Trinidad and Tobago", "Trinidad and Tobago"),
        # Saint Vincent and the Grenadines variations (Canonical: "Saint Vincent and the Grenadines")
        ("St. Vincent / Grenadines", "Saint Vincent and the Grenadines"),
        ("St. Vincent and the Grenadines", "Saint Vincent and the Grenadines"),
        ("Saint Vincent and the Grenadines", "Saint Vincent and the Grenadines"),
        # Saint Kitts and Nevis variations (Canonical: "Saint Kitts and Nevis")
        ("St. Kitts and Nevis", "Saint Kitts and Nevis"),
        ("Saint Kitts and Nevis", "Saint Kitts and Nevis"),
        # UEFA canonical nations
        ("England", "England"),
        ("France", "France"),
        ("Germany", "Germany"),
        ("Spain", "Spain"),
        ("Italy", "Italy"),
        ("Netherlands", "Netherlands"),
        ("Portugal", "Portugal"),
        ("Belgium", "Belgium"),
        ("Croatia", "Croatia"),
        ("Switzerland", "Switzerland"),
        ("Denmark", "Denmark"),
        # CONMEBOL canonical nations
        ("Brazil", "Brazil"),
        ("Argentina", "Argentina"),
        ("Uruguay", "Uruguay"),
        ("Colombia", "Colombia"),
        # CAF canonical nations
        ("Morocco", "Morocco"),
        ("Senegal", "Senegal"),
        ("Nigeria", "Nigeria"),
        ("Ghana", "Ghana"),
        ("Cameroon", "Cameroon"),
        ("Egypt", "Egypt"),
        # CONCACAF canonical nations
        ("Mexico", "Mexico"),
        ("Canada", "Canada"),
        # AFC canonical nations
        ("Japan", "Japan"),
        ("Australia", "Australia"),
    ]

    def test_variation_count_exceeds_50(self):
        """Verify the test suite tests at least 50 variations."""
        self.assertGreaterEqual(
            len(self.VARIATION_PAIRS),
            50,
            f"Expected at least 50 variation pairs, found {len(self.VARIATION_PAIRS)}",
        )

    def test_teams_match_evaluates_true_for_all_variations(self):
        """Verify teams_match returns True for every variation against canonical name."""
        failures = []
        for variation, canonical in self.VARIATION_PAIRS:
            matched = teams_match(variation, canonical)
            if not matched:
                failures.append((variation, canonical))

        self.assertEqual(
            len(failures),
            0,
            f"teams_match failed on {len(failures)} pairs: {failures}",
        )

    def test_teams_match_symmetry(self):
        """Verify teams_match(a, b) == teams_match(b, a) for all pairs."""
        asymmetric = []
        for variation, canonical in self.VARIATION_PAIRS:
            forward = teams_match(variation, canonical)
            reverse = teams_match(canonical, variation)
            if forward != reverse:
                asymmetric.append((variation, canonical, forward, reverse))

        self.assertEqual(
            len(asymmetric),
            0,
            f"teams_match asymmetric for {len(asymmetric)} pairs: {asymmetric}",
        )

    def test_teams_match_reflexivity(self):
        """Verify teams_match(x, x) is always True."""
        for variation, _ in self.VARIATION_PAIRS:
            self.assertTrue(
                teams_match(variation, variation),
                f"teams_match not reflexive for '{variation}'",
            )

    def test_normalize_team_name_on_known_aliases(self):
        """Verify normalize_team_name correctly resolves mapped aliases.
        Note: Checks explicit aliases present in NATIONAL_TEAM_MAP.
        """
        for alias, canonical in NATIONAL_TEAM_MAP.items():
            normalized = normalize_team_name(alias)
            self.assertEqual(
                normalized,
                canonical,
                f"normalize_team_name('{alias}') expected '{canonical}', got '{normalized}'",
            )

    def test_edge_cases_and_malformed_inputs(self):
        """Verify robust handling of empty strings, None, whitespace, and diacritics."""
        # None and empty
        self.assertEqual(normalize_team_name(None), "")
        self.assertEqual(normalize_team_name(""), "")
        self.assertFalse(teams_match(None, "United States"))
        self.assertFalse(teams_match("United States", None))
        self.assertFalse(teams_match("", "United States"))
        self.assertFalse(teams_match("", ""))

        # Whitespace handling
        self.assertEqual(normalize_team_name("  USA  "), "United States")
        self.assertTrue(teams_match("  USA  ", "United States"))

        # Accents
        self.assertEqual(strip_accents("Côte d'Ivoire"), "cote d'ivoire")
        self.assertEqual(strip_accents("Türkiye"), "turkiye")
        self.assertTrue(teams_match("Côte d'Ivoire", "Ivory Coast"))


class TestAdversarialFindings(unittest.TestCase):
    """Adversarial stress-testing proving remediation of edge cases, gaps, and collisions."""

    def test_bosnia_standalone_in_normalize_team_name(self):
        """Remediated verification: 'Bosnia' standalone is mapped to 'Bosnia and Herzegovina'.
        In results.csv, canonical is 'Bosnia and Herzegovina', so 'Bosnia' must map cleanly.
        """
        result = normalize_team_name("Bosnia")
        self.assertEqual(
            result,
            "Bosnia and Herzegovina",
            "Verifies 'Bosnia' is mapped to 'Bosnia and Herzegovina' in NATIONAL_TEAM_MAP",
        )

    def test_case_sensitivity_gap_in_normalization(self):
        """Remediated verification: normalize_team_name is case-insensitive, supporting lowercase alias matching.
        - normalize_team_name('usa') returns 'United States'
        - teams_match('usa', 'United States') returns True
        - teams_match('czechia', 'Czech Republic') returns True
        - teams_match(\"cote d'ivoire\", 'Ivory Coast') returns True
        """
        self.assertEqual(normalize_team_name("usa"), "United States")
        self.assertTrue(
            teams_match("usa", "United States"),
            "Remediated: lowercase 'usa' matches 'United States'",
        )
        self.assertTrue(
            teams_match("czechia", "Czech Republic"),
            "Remediated: lowercase 'czechia' matches 'Czech Republic'",
        )
        self.assertTrue(
            teams_match("cote d'ivoire", "Ivory Coast"),
            "Remediated: lowercase 'cote d\\'ivoire' matches 'Ivory Coast'",
        )

    def test_sovereign_nation_collision_false_positives(self):
        """Remediated verification: teams_match eliminates false-positive matches between distinct sovereign nations and clubs.
        - Niger vs Nigeria
        - South Korea vs North Korea
        - Republic of Ireland vs Northern Ireland
        - Congo vs DR Congo
        - Sudan vs South Sudan
        - Guinea vs Guinea-Bissau
        - Guinea vs Equatorial Guinea
        """
        distinct_nation_pairs = [
            ("Niger", "Nigeria"),
            ("South Korea", "North Korea"),
            ("Republic of Ireland", "Northern Ireland"),
            ("Congo", "DR Congo"),
            ("Sudan", "South Sudan"),
            ("Guinea", "Guinea-Bissau"),
            ("Guinea", "Equatorial Guinea"),
        ]

        collisions = []
        for n1, n2 in distinct_nation_pairs:
            matched = teams_match(n1, n2)
            if matched:
                collisions.append((n1, n2))

        # We assert that 0 pairs collide, confirming the fix:
        self.assertEqual(
            len(collisions),
            0,
            f"Expected 0 distinct sovereign nation pairs to collide, collided {len(collisions)}: {collisions}",
        )


if __name__ == "__main__":
    unittest.main()
