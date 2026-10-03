"""Credential handling: lookup order, placeholders, redaction, and no keys in the source tree."""
import logging
import re
import subprocess
from unittest.mock import patch

from sports_common import secrets
from sports_common.secrets import get_secret, redact, RedactingFormatter

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def test_missing_secret_returns_none():
    assert get_secret("ODDS_API_KEY") is None


def test_env_var_wins_over_files(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text('ODDS_API_KEY="from-dotenv-123"\n')
    monkeypatch.setattr(secrets, "ENV_FILE", env_file)
    secrets._file_secrets.cache_clear()
    assert get_secret("ODDS_API_KEY") == "from-dotenv-123"

    monkeypatch.setenv("ODDS_API_KEY", "from-env-456")
    assert get_secret("ODDS_API_KEY") == "from-env-456"


def test_placeholder_env_var_disables_provider_without_falling_through(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("ODDS_API_KEY=real-looking-key-789\n")
    monkeypatch.setattr(secrets, "ENV_FILE", env_file)
    secrets._file_secrets.cache_clear()
    for placeholder in ("invalid", "", "  none ", "DUMMY"):
        monkeypatch.setenv("ODDS_API_KEY", placeholder)
        assert get_secret("ODDS_API_KEY") is None


def test_dotenv_parsing_handles_comments_export_and_quotes(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("# comment\nexport GEMINI_API_KEY='abc def'\nAPI_FOOTBALL_KEY = xyz\n\nNOEQUALS\n")
    monkeypatch.setattr(secrets, "ENV_FILE", env_file)
    secrets._file_secrets.cache_clear()
    assert get_secret("GEMINI_API_KEY") == "abc def"
    assert get_secret("API_FOOTBALL_KEY") == "xyz"


def test_legacy_streamlit_secrets_are_still_read(tmp_path, monkeypatch):
    toml_file = tmp_path / "secrets.toml"
    toml_file.write_text('API_FOOTBALL_KEY = "toml-key-1234"\n')
    monkeypatch.setattr(secrets, "LEGACY_SECRETS_FILE", toml_file)
    secrets._file_secrets.cache_clear()
    assert get_secret("API_FOOTBALL_KEY") == "toml-key-1234"


def test_redact_masks_query_params_and_configured_values(monkeypatch):
    monkeypatch.setenv("API_FOOTBALL_KEY", "supersecretvalue42")
    text = "401 for url: https://x/v4/sports/?apiKey=abcdef123&regions=eu header supersecretvalue42"
    out = redact(text)
    assert "abcdef123" not in out and "supersecretvalue42" not in out
    assert "apiKey=***" in out and "regions=eu" in out


def test_redacting_formatter_masks_tracebacks():
    formatter = RedactingFormatter(logging.Formatter("%(message)s"))
    try:
        raise RuntimeError("failed GET https://api/x?apiKey=leaky0123456789")
    except RuntimeError:
        import sys
        record = logging.LogRecord("t", logging.ERROR, __file__, 1, "boom", None, sys.exc_info())
    out = formatter.format(record)
    assert "leaky0123456789" not in out
    assert "RuntimeError" in out


def test_odds_client_without_key_uses_espn_and_never_calls_odds_api():
    from football_core.data import odds_api

    with patch.object(odds_api.requests, "get") as odds_get, \
         patch("football_core.data.espn_client.fetch_espn_upcoming_fixtures", return_value=[{"m": 1}]) as espn:
        assert odds_api.get_odds_api_key() == ""
        assert odds_api.fetch_league_odds("EPL") == [{"m": 1}]
        odds_get.assert_not_called()
        espn.assert_called_once_with("EPL")


def test_api_football_without_key_makes_no_requests():
    from football_core.data import api_football

    with patch.object(api_football.requests, "get") as get:
        assert api_football.fetch_api_football_status()["ok"] is False
        assert api_football.fetch_fixtures_by_date("2099-01-01", force=True) == []
        get.assert_not_called()


def test_tennis_clients_without_key_make_no_requests():
    from tennis_core.data import odds_api, scraper, auto_reconcile

    with patch.object(odds_api.requests, "get") as get1, \
         patch.object(scraper.requests, "get") as get2, \
         patch.object(auto_reconcile.requests, "get") as get3:
        assert odds_api.fetch_all_live_tennis_matches() == []
        assert scraper.fetch_odds_api_quota()["ok"] is False
        assert auto_reconcile.fetch_odds_api_tennis_scores() == []
        get1.assert_not_called(); get2.assert_not_called(); get3.assert_not_called()


def test_no_hardcoded_api_keys_in_tracked_source():
    """Fail if a 32+ char hex literal is assigned to anything that looks like a key or token."""
    files = subprocess.run(
        ["git", "ls-files", "*.py", "*.ts", "*.tsx", "*.js", "*.yml", "*.toml", "*.md"],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    pattern = re.compile(r"(?i)(key|token|secret)\w*\s*[:=]\s*['\"][0-9a-f]{32,}['\"]")
    offenders = []
    for rel in files:
        path = PROJECT_ROOT / rel
        if not path.exists() or rel.startswith("tests/test_secrets.py"):
            continue
        for n, line in enumerate(path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
            if pattern.search(line) and "0123456789abcdef" not in line:
                offenders.append(f"{rel}:{n}")
    assert offenders == []
