"""Workspace creation and atomic JSON helpers."""
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def ensure_workspace(workspace_dir: Path) -> None:
    """Create workspace root if it does not exist."""
    workspace_dir.mkdir(parents=True, exist_ok=True)


def create_job_directory(workspace_dir: Path, job_id: str) -> Path:
    """Create and return the directory tree for a new job."""
    job_dir = workspace_dir / job_id
    for subdir in ("audio", "audio/chunks", "transcript", "transcript/chunks", "summary"):
        (job_dir / subdir).mkdir(parents=True, exist_ok=True)
    return job_dir


def atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """Write JSON atomically using a temp file and replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def atomic_write_text(path: Path, text: str) -> None:
    """Write UTF-8 text atomically using a temp file and replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(temp_path, path)
    except Exception:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def read_json(path: Path) -> dict[str, Any]:
    """Read a JSON file."""
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)
