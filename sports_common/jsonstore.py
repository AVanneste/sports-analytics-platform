"""Crash-safe JSON persistence for the prediction ledgers.

* ``write_json_atomic`` writes to a temp file in the same directory, fsyncs it and
  ``os.replace``s it over the target, so a crash leaves either the old or the new file,
  never a truncated one.
* ``read_json`` raises :class:`LedgerCorruptError` for an unreadable file instead of
  returning an empty default, so callers cannot silently overwrite history with ``[]``.
* ``daily_backup`` keeps one dated copy per day (pruned to the newest ``keep``).
"""
import json
import os
import shutil
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Callable, Optional


class LedgerCorruptError(RuntimeError):
    """A ledger file exists but cannot be parsed; refuse to continue rather than lose data."""


def read_json(path: Path, default: Any = None, validate: Optional[Callable[[Any], bool]] = None) -> Any:
    """Return the parsed JSON at ``path``; ``default`` only when the file does not exist."""
    path = Path(path)
    if not path.exists():
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        raise LedgerCorruptError(
            f"Cannot read {path}: {e}. Restore it from {path.parent / 'backups'} or git history."
        ) from e
    if validate is not None and not validate(data):
        raise LedgerCorruptError(f"Unexpected structure in {path}; refusing to load it.")
    return data


def write_json_atomic(path: Path, data: Any, indent: int = 2, default: Optional[Callable] = None) -> None:
    """Serialise ``data`` to ``path`` atomically (temp file + fsync + rename)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=indent, default=default)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        raise
    try:  # make the rename itself durable (best effort; not supported everywhere)
        dir_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass


def daily_backup(path: Path, backup_dir: Optional[Path] = None, keep: int = 14) -> Optional[Path]:
    """Copy ``path`` to ``backup_dir/<stem>.<YYYY-MM-DD><suffix>`` once per day; prune old copies."""
    path = Path(path)
    if not path.exists():
        return None
    backup_dir = Path(backup_dir) if backup_dir else path.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    target = backup_dir / f"{path.stem}.{date.today().isoformat()}{path.suffix}"
    if not target.exists():
        shutil.copy2(path, target)
    copies = sorted(backup_dir.glob(f"{path.stem}.????-??-??{path.suffix}"))
    for old in copies[:-keep] if keep > 0 else []:
        old.unlink(missing_ok=True)
    return target
