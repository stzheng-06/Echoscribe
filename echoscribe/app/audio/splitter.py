"""Fixed-time local audio splitting through optional FFmpeg."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import wave

from app.audio.converter import CommandRunner, _run_command, find_ffmpeg, require_ffmpeg
from app.audio.probe import probe_audio
from app.exceptions import AudioConversionError, OperationCancelled


@dataclass(frozen=True)
class AudioChunk:
    chunk_id: int
    path: Path
    start_seconds: float
    end_seconds: float


def split_audio(
    source: Path,
    output_dir: Path,
    *,
    chunk_minutes: int = 10,
    overlap_seconds: float = 2,
    ffmpeg_path: Path | None = None,
    command_runner: CommandRunner | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> list[AudioChunk]:
    """Create sequential WAV chunks, reusing valid files from earlier attempts."""
    metadata = probe_audio(source)
    if metadata.duration_seconds is None:
        raise AudioConversionError("Audio duration is required for local chunking")
    chunk_seconds = min(float(chunk_minutes * 60), 600.0)
    if chunk_seconds <= 0 or overlap_seconds < 0 or overlap_seconds >= chunk_seconds:
        raise AudioConversionError("Chunk duration must be greater than the overlap")

    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[AudioChunk] = []
    start = 0.0
    chunk_id = 0
    executable: Path | None = ffmpeg_path or find_ffmpeg()
    if source.suffix.casefold() == ".wav" and executable is None and command_runner is None:
        chunk_seconds = _native_wave_chunk_seconds(source, chunk_seconds)
        if overlap_seconds >= chunk_seconds:
            raise AudioConversionError("PCM WAV bitrate leaves no room for the overlap")
    while start < metadata.duration_seconds:
        if is_cancelled and is_cancelled():
            raise OperationCancelled("Audio splitting was cancelled")
        end = min(start + chunk_seconds, metadata.duration_seconds)
        path = output_dir / f"chunk_{chunk_id:03d}.wav"
        chunk = AudioChunk(chunk_id, path, start, end)
        chunks.append(chunk)
        if not path.exists() or path.stat().st_size == 0:
            native_wave = False
            if (
                source.suffix.casefold() == ".wav"
                and executable is None
                and command_runner is None
            ):
                try:
                    _write_pcm_wave_chunk(source, path, start, end - start)
                    native_wave = True
                except (OSError, EOFError, wave.Error):
                    native_wave = False
            if not native_wave:
                executable = require_ffmpeg(executable)
                command = [
                    str(executable),
                    "-hide_banner",
                    "-loglevel",
                    "error",
                    "-y",
                    "-ss",
                    f"{start:.3f}",
                    "-i",
                    str(source),
                    "-t",
                    f"{end - start:.3f}",
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-acodec",
                    "pcm_s16le",
                    str(path),
                ]
                (command_runner or _run_command)(command)
            if not path.exists() or path.stat().st_size == 0:
                raise AudioConversionError(f"FFmpeg did not create chunk {chunk_id}")
        if end >= metadata.duration_seconds:
            break
        start = end - overlap_seconds
        chunk_id += 1
    return chunks


def _native_wave_chunk_seconds(source: Path, requested_seconds: float) -> float:
    """Cap native PCM chunks below a conservative 20 MiB upload size."""
    with wave.open(str(source), "rb") as reader:
        bytes_per_second = (
            reader.getframerate() * reader.getnchannels() * reader.getsampwidth()
        )
    if bytes_per_second <= 0:
        raise wave.Error("Invalid PCM WAV rate")
    return min(requested_seconds, (20 * 1024 * 1024) / bytes_per_second)


def _write_pcm_wave_chunk(
    source: Path, destination: Path, start_seconds: float, duration_seconds: float
) -> None:
    """Split an uncompressed WAV without FFmpeg or loading it fully into memory."""
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    try:
        with wave.open(str(source), "rb") as reader:
            if reader.getcomptype() != "NONE":
                raise wave.Error("Compressed WAV requires FFmpeg")
            frame_rate = reader.getframerate()
            start_frame = min(round(start_seconds * frame_rate), reader.getnframes())
            frames_remaining = min(
                round(duration_seconds * frame_rate), reader.getnframes() - start_frame
            )
            reader.setpos(start_frame)
            with wave.open(str(temporary), "wb") as writer:
                writer.setnchannels(reader.getnchannels())
                writer.setsampwidth(reader.getsampwidth())
                writer.setframerate(frame_rate)
                while frames_remaining > 0:
                    frame_count = min(frames_remaining, 65_536)
                    data = reader.readframes(frame_count)
                    if not data:
                        break
                    writer.writeframesraw(data)
                    frames_remaining -= frame_count
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
