"""Credential lookup and log redaction shared by both sports.

Lookup order for a secret:
  1. the process environment (CI injects GitHub Actions secrets here),
  2. ``.env`` at the repository root,
  3. the legacy ``.streamlit/secrets.toml`` (kept so existing local setups still work).

There is deliberately no hardcoded fallback: a missing key means the corresponding
provider is skipped and callers fall back to the free sources (ESPN, tennis-data.co.uk).
"""
import logging
import os
import re
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Dict, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
LEGACY_SECRETS_FILE = PROJECT_ROOT / ".streamlit" / "secrets.toml"

# Values that mean "deliberately disabled" (e.g. ODDS_API_KEY=invalid forces the ESPN path).
PLACEHOLDER_VALUES = {"", "none", "null", "invalid", "false", "test", "dummy"}

KNOWN_SECRET_NAMES = ("ODDS_API_KEY", "API_FOOTBALL_KEY", "GEMINI_API_KEY")

_QUERY_KEY_RE = re.compile(r"(?i)\b(api_?key|key|token)=([^&\s'\"]+)")


def _parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        name, _, value = line.partition("=")
        values[name.strip()] = value.strip().strip('"').strip("'")
    return values


@lru_cache(maxsize=1)
def _file_secrets() -> Dict[str, str]:
    values: Dict[str, str] = {}
    if LEGACY_SECRETS_FILE.exists():
        try:
            with open(LEGACY_SECRETS_FILE, "rb") as f:
                values.update({k: str(v) for k, v in tomllib.load(f).items() if not isinstance(v, dict)})
        except (OSError, tomllib.TOMLDecodeError):
            pass
    if ENV_FILE.exists():
        try:
            values.update(_parse_env_file(ENV_FILE))
        except OSError:
            pass
    return values


def get_secret(name: str) -> Optional[str]:
    """Return the configured value for ``name``, or None when unset or a placeholder.

    An environment variable always wins, even when it is a placeholder: setting
    ``ODDS_API_KEY=invalid`` disables the provider instead of falling through to files.
    """
    value = os.environ[name] if name in os.environ else _file_secrets().get(name)
    value = (value or "").strip()
    if value.lower() in PLACEHOLDER_VALUES:
        return None
    return value


def is_usable_key(value: Optional[str]) -> bool:
    """True when ``value`` looks like a real credential rather than empty/placeholder text."""
    return bool(value) and str(value).strip().lower() not in PLACEHOLDER_VALUES


def redact(text: object) -> str:
    """Mask configured secret values and ``apiKey=...`` style query parameters in ``text``."""
    out = str(text)
    for name in KNOWN_SECRET_NAMES:
        value = get_secret(name)
        if value and len(value) >= 8:
            out = out.replace(value, "***")
    return _QUERY_KEY_RE.sub(lambda m: f"{m.group(1)}=***", out)


class RedactingFormatter(logging.Formatter):
    """Wraps another formatter and applies :func:`redact` to its output, tracebacks included."""

    def __init__(self, inner: Optional[logging.Formatter] = None):
        super().__init__()
        self._inner = inner or logging.Formatter()

    def format(self, record: logging.LogRecord) -> str:
        return redact(self._inner.format(record))


def install_log_redaction(logger: Optional[logging.Logger] = None) -> None:
    """Wrap the formatters of ``logger``'s handlers (root by default) with secret redaction."""
    target = logger or logging.getLogger()
    for handler in target.handlers:
        if not isinstance(handler.formatter, RedactingFormatter):
            handler.setFormatter(RedactingFormatter(handler.formatter))
