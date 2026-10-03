"""Shared pytest configuration.

Every test runs with credentials stripped: real keys from the environment, ``.env`` or
``.streamlit/secrets.toml`` are never visible, so no test can hit a paid API by accident.
"""
import pytest

from sports_common import secrets as _secrets


@pytest.fixture(autouse=True)
def _no_real_secrets(tmp_path, monkeypatch):
    for name in _secrets.KNOWN_SECRET_NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(_secrets, "ENV_FILE", tmp_path / "absent.env")
    monkeypatch.setattr(_secrets, "LEGACY_SECRETS_FILE", tmp_path / "absent_secrets.toml")
    _secrets._file_secrets.cache_clear()
    yield
    _secrets._file_secrets.cache_clear()
