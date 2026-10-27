"""Optional FFmpeg discovery and audio conversion."""
from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path

from app.exceptions import AudioConversionError

CommandRunner = Callable[[Sequence[str]], None]


def find_ffmpeg() -> Path | None:
    """Return the FFmpeg executable on PATH, if available."""
    executable = shutil.which("ffmpeg")
    return Path(executable) if executable else None


def require_ffmpeg(ffmpeg_path: Path | None = None) -> Path:
    """Resolve FFmpeg or raise a user-facing optional-dependency error."""
    resolved = ffmpeg_path or find_ffmpeg()
    if resolved is None:
        raise AudioConversionError(
            "FFmpeg is required for local chunking. Install it and add ffmpeg to PATH, "
            "or enable provider automatic chunking in Settings."
        )
    return resolved


def convert_to_wav(
    source: Path,
    destination: Path,
    *,
    ffmpeg_path: Path | None = None,
    command_runner: CommandRunner | None = None,
) -> Path:
    """Convert one media file to PCM WAV without loading it into memory."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    executable = require_ffmpeg(ffmpeg_path)
    command = [
        str(executable),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source),
        "-vn",
        "-acodec",
        "pcm_s16le",
        str(destination),
    ]
    (command_runner or _run_command)(command)
    if not destination.exists() or destination.stat().st_size == 0:
        raise AudioConversionError("FFmpeg did not create the converted audio file")
    return destination


def _run_command(command: Sequence[str]) -> None:
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            **_subprocess_window_options(),
        )
    except FileNotFoundError as exc:
        raise AudioConversionError("FFmpeg executable was not found") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        message = "FFmpeg audio processing failed"
        if detail:
            message = f"{message}: {detail[-500:]}"
        raise AudioConversionError(message) from exc


def _subprocess_window_options(platform_name: str | None = None) -> dict[str, int]:
    """Prevent FFmpeg from flashing a console window in the Windows GUI app."""
    if (platform_name or os.name) != "nt":
        return {}
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)}
