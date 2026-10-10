"""Append-only, atomic writes to data files, plus resumable annotation drafts.

The annotation and collection tools never edit or delete an existing record. A new
record is appended by writing the complete file to a temporary path and then
atomically replacing the original, so an interruption (Ctrl+C, crash, power loss)
leaves either the old file or the new file -- never a half-written one.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any

DRAFTS_DIRNAME = ".drafts"


class StorageError(RuntimeError):
    """Raised when a data file cannot be safely read or appended to."""


def _read_list(path: Path) -> list[Any]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise StorageError(f"{path} is not valid JSON (line {exc.lineno}); fix it first") from exc
    if not isinstance(data, list):
        raise StorageError(f"{path} must contain a JSON array")
    return data


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON (UTF-8, LF, 2-space indent) via a temp file and atomic replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def append_record(path: Path, record: dict[str, Any], id_field: str) -> None:
    """Append ``record`` to the JSON array in ``path``; refuse duplicate IDs.

    Existing records are written back exactly as they were parsed, so earlier
    annotations cannot be modified through this function.
    """
    records = _read_list(path)
    new_id = record[id_field]
    if any(isinstance(r, dict) and r.get(id_field) == new_id for r in records):
        raise StorageError(f"{path.name} already contains {id_field} '{new_id}'; nothing written")
    write_json_atomic(path, [*records, record])


def next_id(path: Path, id_field: str, prefix: str, width: int = 4) -> str:
    """Return the first unused ID of the form ``<prefix><zero-padded number>``."""
    used = {r.get(id_field) for r in _read_list(path) if isinstance(r, dict)}
    n = 1
    while f"{prefix}{n:0{width}d}" in used:
        n += 1
    return f"{prefix}{n:0{width}d}"


class DraftStore:
    """Partial annotations saved after every answer so an interrupted session can resume.

    Drafts live in ``<data_dir>/.drafts/`` (git-ignored). They are working files, not
    data: validation and reporting never read them.
    """

    def __init__(self, data_dir: Path) -> None:
        self.directory = data_dir / DRAFTS_DIRNAME

    def path(self, key: str) -> Path:
        return self.directory / f"{key}.json"

    def load(self, key: str) -> dict[str, Any] | None:
        path = self.path(key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise StorageError(f"draft {path} is corrupt; delete it to start over") from exc
        return data if isinstance(data, dict) else None

    def save(self, key: str, data: dict[str, Any]) -> None:
        write_json_atomic(self.path(key), data)

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

    def keys(self, prefix: str = "") -> list[str]:
        if not self.directory.is_dir():
            return []
        return sorted(p.stem for p in self.directory.glob(f"{prefix}*.json"))
