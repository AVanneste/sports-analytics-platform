"""Adversarial Test Suite for Milestone 1: Free Data Source Integration & League Configuration.

Empirical verification of:
1. american_to_decimal edge cases, extreme values, malformations, and boundary values.
2. is_valid_odds_api_key validation with dummy, placeholder, and malicious strings.
3. Quota exhaustion and ODDS_API_KEY=invalid fallback routing without hanging or crashing.
"""

import math
import os
import sys
import time
import unittest
from unittest.mock import patch, MagicMock

# Ensure Football module is importable
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FOOTBALL_DIR = os.path.join(REPO_ROOT, "Football")
if FOOTBALL_DIR not in sys.path:
    sys.path.insert(0, FOOTBALL_DIR)

from football_core.config import LEAGUES
from football_core.data.espn_client import (
    ESPN_LEAGUE_CODES,
    american_to_decimal,
    fetch_espn_upcoming_fixtures,
)
from football_core.data.odds_api import (
    is_valid_odds_api_key,
    fetch_league_odds,
    fetch_all_live_upcoming_fixtures,
    get_odds_api_key,
    DEFAULT_ODDS_API_KEY,
)


class TestAmericanToDecimalAdversarial(unittest.TestCase):
    """Adversarial stress-testing of american_to_decimal."""

    def test_standard_positive_and_negative_moneylines(self):
        """Test +/-100 and +/-110 standard lines."""
        # 100 / +100 -> 1 + 100/100 = 2.00
        self.assertEqual(american_to_decimal(100), 2.00)
        self.assertEqual(american_to_decimal("+100"), 2.00)
        self.assertEqual(american_to_decimal("100"), 2.00)

        # -100 -> 1 + 100/100 = 2.00
        self.assertEqual(american_to_decimal(-100), 2.00)
        self.assertEqual(american_to_decimal("-100"), 2.00)
        # Unicode minus character
        self.assertEqual(american_to_decimal("−100"), 2.00)

        # 110 / +110 -> 1 + 110/100 = 2.10
        self.assertEqual(american_to_decimal(110), 2.10)
        self.assertEqual(american_to_decimal("+110"), 2.10)
        self.assertEqual(american_to_decimal("110"), 2.10)

        # -110 -> 1 + 100/110 = 1.9090... -> 1.91
        self.assertEqual(american_to_decimal(-110), 1.91)
        self.assertEqual(american_to_decimal("-110"), 1.91)
        self.assertEqual(american_to_decimal("−110"), 1.91)

    def test_even_and_pick_keywords(self):
        """Test keyword representations for even money (EVEN, EV, PK, PICK)."""
        keywords = ["EVEN", "EV", "PK", "PICK", "even", "ev", "pk", "pick", "Even", "Pick"]
        for kw in keywords:
            with self.subTest(keyword=kw):
                self.assertEqual(american_to_decimal(kw), 2.00)
                self.assertEqual(american_to_decimal(f"  {kw}  "), 2.00)
                self.assertEqual(american_to_decimal(f"\t{kw}\n"), 2.00)

    def test_already_decimal_representations(self):
        """Test values already formatted in decimal odds."""
        # Decimal strings
        self.assertEqual(american_to_decimal("1.85"), 1.85)
        self.assertEqual(american_to_decimal("2.50"), 2.50)
        self.assertEqual(american_to_decimal("1.05"), 1.05)
        self.assertEqual(american_to_decimal("99.50"), 99.50)

        # Decimal floats
        self.assertEqual(american_to_decimal(1.85), 1.85)
        self.assertEqual(american_to_decimal(2.50), 2.50)
        self.assertEqual(american_to_decimal(1.05), 1.05)
        self.assertEqual(american_to_decimal(99.50), 99.50)

    def test_extreme_values(self):
        """Test large positive/negative numbers, limits, and potential overflow/underflow."""
        # Large favorite (-1000000): 1 + 100/1000000 = 1.0001 -> 1.0
        self.assertEqual(american_to_decimal(-1000000), 1.0)
        self.assertEqual(american_to_decimal("-1000000"), 1.0)

        # Large underdog (+1000000): 1 + 1000000/100 = 10001.0
        self.assertEqual(american_to_decimal(1000000), 10001.0)
        self.assertEqual(american_to_decimal("+1000000"), 10001.0)

        # Scientific notation
        self.assertEqual(american_to_decimal("1e4"), 101.0)
        self.assertEqual(american_to_decimal("-1e4"), 1.01)

        # Extreme magnitudes
        self.assertIsNotNone(american_to_decimal(1e12))
        self.assertIsNotNone(american_to_decimal(-1e12))

    def test_infinity_and_nan(self):
        """Test inf, -inf, nan handling."""
        self.assertIsNone(american_to_decimal(float("nan")))
        self.assertIsNone(american_to_decimal("nan"))
        self.assertIsNone(american_to_decimal("NaN"))
        self.assertIsNone(american_to_decimal(float("inf")))
        self.assertIsNone(american_to_decimal("inf"))
        self.assertIsNone(american_to_decimal(float("-inf")))
        self.assertIsNone(american_to_decimal("-inf"))

    def test_malformed_and_boundary_inputs(self):
        """Test malformed strings, None, 0, whitespace, and type invariants."""
        malformed = [
            "+abc",
            "-xyz",
            "abc",
            "",
            "   ",
            "\n\t\r",
            None,
            0,
            "0",
            0.0,
            "-0.0",
            "++100",
            "--100",
            "+-100",
            "100+",
            "100-",
            "$100",
            "#100",
            "\x00",
            "100\x00",
            True,
            False,
            [],
            {},
            [100],
            {"odds": 100},
            1 + 2j,
            object(),
        ]
        for val in malformed:
            with self.subTest(val=val):
                res = american_to_decimal(val)
                self.assertIsNone(res, f"Expected None for malformed input {val!r}, got {res!r}")

    def test_invalid_range_and_sub_decimal(self):
        """Values between 0 and 1.01 (odds cannot be <= 1.00 since returns would be 0 or negative)."""
        invalid_odds = [1.00, 0.99, 0.50, 0.01, -0.5, -50]
        for val in invalid_odds:
            with self.subTest(val=val):
                res = american_to_decimal(val)
                self.assertIsNone(res, f"Expected None for invalid betting odds {val!r}, got {res!r}")


class TestIsValidOddsApiKeyAdversarial(unittest.TestCase):
    """Adversarial stress-testing of is_valid_odds_api_key."""

    def test_known_valid_keys(self):
        """Standard 32-character hexadecimal API keys should be accepted."""
        valid_keys = [
            DEFAULT_ODDS_API_KEY,
            "0123456789abcdef0123456789abcdef",
            "2248b63df4643a6eb03b7918e9cb3226",
            "  2248b63df4643a6eb03b7918e9cb3226  ",
        ]
        for k in valid_keys:
            with self.subTest(key=k):
                self.assertTrue(is_valid_odds_api_key(k))

    def test_dummy_and_placeholder_values(self):
        """Known placeholders, empty strings, and dummy tokens must return False."""
        dummy_keys = [
            None,
            "",
            "   ",
            "\t\n\r",
            "invalid",
            "INVALID",
            "  invalid  ",
            "none",
            "None",
            "NONE",
            "  none  ",
            "null",
            "Null",
            "NULL",
            "false",
            "False",
            "FALSE",
            "test",
            "TEST",
            "dummy",
            "DUMMY",
            "  dummy  ",
            False,
            0,
            [],
            {},
        ]
        for k in dummy_keys:
            with self.subTest(key=k):
                self.assertFalse(is_valid_odds_api_key(k), f"Expected False for dummy key {k!r}")

    def test_malicious_and_injection_strings_do_not_crash(self):
        """Malicious inputs (SQL injection, path traversal, control chars) must not crash the validator."""
        malicious = [
            "'; DROP TABLE users; --",
            "../../etc/passwd",
            "<script>alert(1)</script>",
            "test\x00key",
            "test\nkey",
            "test\r\nkey",
            "a" * 100000,
            "`rm -rf /`",
            "$(whoami)",
            "& ping 127.0.0.1",
        ]
        for s in malicious:
            with self.subTest(string=s[:30]):
                try:
                    res = is_valid_odds_api_key(s)
                    self.assertIsInstance(res, bool)
                except Exception as e:
                    self.fail(f"is_valid_odds_api_key crashed on {s!r}: {e}")


class TestQuotaExhaustionAndFallbackRouting(unittest.TestCase):
    """Stress-test quota exhaustion and ODDS_API_KEY=invalid fallback routing."""

    def setUp(self):
        self.domestic_leagues = ["EPL", "LaLiga", "Bundesliga", "SerieA", "Ligue1"]
        self.international_leagues = [
            "NationsLeague", "WorldCup", "WCQ_UEFA", "WCQ_CONMEBOL",
            "WCQ_CAF", "Euro", "CopaAmerica", "AFCON", "Friendlies", "GoldCup"
        ]

    def test_all_22_leagues_configured(self):
        """Verify all 22 competitions are registered and mapped properly."""
        self.assertEqual(len(LEAGUES), 22)
        for league_key in self.international_leagues:
            info = LEAGUES[league_key]
            self.assertTrue(info.get("is_cup"))
            self.assertTrue(info.get("is_international"))
            self.assertIsNone(info.get("odds_key"))
            self.assertEqual(info.get("espn_code"), ESPN_LEAGUE_CODES[league_key])

        for league_key in self.domestic_leagues:
            info = LEAGUES[league_key]
            self.assertIsNotNone(info.get("odds_key"))
            self.assertEqual(info.get("espn_code"), ESPN_LEAGUE_CODES[league_key])

    @patch("football_core.data.espn_client._espn_get_json")
    @patch("football_core.data.odds_api.requests.get")
    def test_invalid_key_bypasses_odds_api_and_routes_to_espn_instantly(self, mock_odds_get, mock_espn_get):
        """When api_key='invalid', The Odds API must never be called; ESPN must be called."""
        # Setup mock ESPN response to simulate real scheduled matches
        mock_espn_get.return_value = {
            "events": [
                {
                    "id": "12345",
                    "date": "2026-10-15T19:45:00Z",
                    "competitions": [
                        {
                            "competitors": [
                                {"homeAway": "home", "team": {"displayName": "France"}},
                                {"homeAway": "away", "team": {"displayName": "Germany"}}
                            ],
                            "status": {"type": {"completed": False}}
                        }
                    ]
                }
            ]
        }

        # Test both domestic and international leagues
        all_leagues = self.domestic_leagues + self.international_leagues
        for league in all_leagues:
            with self.subTest(league=league):
                t0 = time.time()
                fixtures = fetch_league_odds(league, api_key="invalid")
                elapsed = time.time() - t0

                # Must return a list
                self.assertIsInstance(fixtures, list)
                # Must complete swiftly (< 100ms when network is mocked)
                self.assertLess(elapsed, 0.10)
                # The Odds API requests.get must NEVER have been called!
                mock_odds_get.assert_not_called()

        # Verify ESPN was queried
        self.assertGreater(mock_espn_get.call_count, 0)

    @patch("football_core.data.espn_client._espn_get_json")
    @patch("football_core.data.odds_api.requests.get")
    @patch("football_core.data.odds_api.get_stored_quota")
    def test_quota_exhausted_bypasses_odds_api_and_routes_to_espn(
        self, mock_get_quota, mock_odds_get, mock_espn_get
    ):
        """When quota is exhausted (ok=False or remaining<=0), routing must go directly to ESPN."""
        mock_get_quota.return_value = {"remaining": "0", "used": "500", "ok": False, "status_code": 429}
        mock_espn_get.return_value = {"events": []}

        for league in self.domestic_leagues:
            with self.subTest(league=league):
                t0 = time.time()
                res = fetch_league_odds(league, api_key=DEFAULT_ODDS_API_KEY)
                elapsed = time.time() - t0

                self.assertIsInstance(res, list)
                self.assertLess(elapsed, 0.10)
                # Ensure no HTTP calls were made to The Odds API
                mock_odds_get.assert_not_called()

    @patch("football_core.data.espn_client.fetch_espn_upcoming_fixtures")
    def test_espn_exception_does_not_crash_fetch_league_odds(self, mock_espn_fetch):
        """If ESPN client throws an exception, fetch_league_odds should return [] gracefully."""
        mock_espn_fetch.side_effect = RuntimeError("ESPN connection failed")

        for league in ["EPL", "NationsLeague"]:
            with self.subTest(league=league):
                try:
                    res = fetch_league_odds(league, api_key="invalid")
                    self.assertEqual(res, [])
                except Exception as e:
                    self.fail(f"fetch_league_odds crashed on ESPN exception: {e}")

    def test_unknown_league_key_handled_safely(self):
        """Unknown league keys should return [] without crashing."""
        self.assertEqual(fetch_league_odds("NonExistentLeague123"), [])
        self.assertEqual(fetch_league_odds(""), [])
        self.assertEqual(fetch_league_odds(None), [])

    @patch("football_core.data.espn_client._espn_get_json")
    def test_espn_empty_competitions_vulnerability(self, mock_espn_get):
        """Verify empty 'competitions': [] in event shell is safely skipped without IndexError."""
        mock_espn_get.return_value = {
            "events": [
                {"id": "bad_event_shell", "competitions": []}
            ]
        }
        res = fetch_espn_upcoming_fixtures("EPL")
        self.assertEqual(res, [])

    @patch("football_core.data.espn_client._espn_get_json")
    def test_espn_upcoming_fixtures_payload_contract(self, mock_espn_get):
        """Verify upcoming fixtures payload includes 'bookmaker': 'DraftKings (ESPN)' and parses odds."""
        mock_espn_get.return_value = {
            "events": [
                {
                    "id": "match_100",
                    "date": "2026-10-15T19:45:00Z",
                    "competitions": [
                        {
                            "competitors": [
                                {"homeAway": "home", "team": {"displayName": "Arsenal"}},
                                {"homeAway": "away", "team": {"displayName": "Chelsea"}},
                            ],
                            "status": {"type": {"completed": False}},
                            "neutralSite": False,
                            "odds": [
                                {
                                    "moneyline": {
                                        "home": {"close": {"odds": "+150"}},
                                        "draw": {"close": {"odds": "+220"}},
                                        "away": {"close": {"odds": "+180"}},
                                    },
                                    "total": {
                                        "over": {"close": {"odds": "-110"}},
                                        "under": {"close": {"odds": "-110"}},
                                    },
                                }
                            ],
                        }
                    ],
                }
            ]
        }
        fixtures = fetch_espn_upcoming_fixtures("EPL")
        self.assertEqual(len(fixtures), 1)
        self.assertEqual(fixtures[0]["bookmaker"], "DraftKings (ESPN)")
        self.assertEqual(fixtures[0]["odds_home"], 2.50)
        self.assertEqual(fixtures[0]["odds_draw"], 3.20)
        self.assertEqual(fixtures[0]["odds_away"], 2.80)
        self.assertEqual(fixtures[0]["odds_over25"], 1.91)
        self.assertEqual(fixtures[0]["odds_under25"], 1.91)

    @patch("football_core.data.espn_client._espn_get_json")
    def test_fetch_league_odds_shields_against_espn_malformed_event(self, mock_espn_get):
        """Even if ESPN raises IndexError on malformed event shell, fetch_league_odds catches it and returns []."""
        mock_espn_get.return_value = {
            "events": [
                {"id": "bad_event_shell", "competitions": []}
            ]
        }
        res = fetch_league_odds("EPL", api_key="invalid")
        self.assertEqual(res, [])

    @patch("football_core.data.espn_client._espn_get_json")
    @patch("football_core.data.odds_api.requests.get")
    def test_fetch_all_live_upcoming_fixtures_with_invalid_key(self, mock_odds_get, mock_espn_get):
        """Verify fetch_all_live_upcoming_fixtures seamlessly bypasses Odds API when key is invalid."""
        mock_espn_get.return_value = {"events": []}
        fixtures = fetch_all_live_upcoming_fixtures(api_key="invalid", use_cache=False)
        self.assertIsInstance(fixtures, list)
        mock_odds_get.assert_not_called()


if __name__ == "__main__":
    unittest.main(verbosity=2)
