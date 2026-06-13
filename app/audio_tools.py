import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy import signal
from scipy.io import wavfile


OUTPUT_SAMPLE_RATE = 48000
OUTPUT_CHANNELS = 2


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def check_ffmpeg() -> bool:
    return shutil.which("ffmpeg") is not None


@dataclass
class AudioDevice:
    name: str
    kind: str
    alternative_name: str = ""

    def display_text(self) -> str:
        text = f"{self.name} [{self.kind}]"
        if self.alternative_name:
            text += f"\n  替代名: {self.alternative_name}"
        return text


def parse_audio_devices(output: str) -> list[AudioDevice]:
    """Parse FFmpeg dshow device list output into structured audio devices."""
    devices: list[AudioDevice] = []
    last_device: AudioDevice | None = None

    for line in output.splitlines():
        # FFmpeg prefixes every device line with [in#0 @ ...]
        if "[in#" not in line:
            continue

        # Alternative name line
        alt_match = re.search(r'Alternative name "([^"]+)"', line)
        if alt_match and last_device is not None:
            last_device.alternative_name = alt_match.group(1)
            continue

        # Device entry line: "Name" (type)
        dev_match = re.search(r'"([^"]+)"\s*\(([^)]+)\)', line)
        if dev_match:
            name = dev_match.group(1)
            kind = dev_match.group(2)
            device = AudioDevice(name=name, kind=kind)
            devices.append(device)
            last_device = device

    return devices


def list_audio_devices() -> str:
    """Return FFmpeg's raw dshow device list as a string."""
    proc = subprocess.run(
        ["ffmpeg", "-list_devices", "true", "-f", "dshow", "-i", "dummy"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    # FFmpeg writes device list to stderr.
    return proc.stderr or proc.stdout or "无法获取设备列表"


def check_wasapi_support() -> bool:
    """Check if FFmpeg supports WASAPI loopback capture."""
    proc = subprocess.run(
        ["ffmpeg", "-list_devices", "true", "-f", "wasapi", "-i", "dummy"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return "Unknown input format: 'wasapi'" not in proc.stderr


def list_wasapi_devices() -> list[AudioDevice]:
    """List Windows audio output devices for WASAPI loopback capture.

    Returns empty list if FFmpeg doesn't support WASAPI.
    """
    if not check_wasapi_support():
        return []

    proc = subprocess.run(
        ["ffmpeg", "-list_devices", "true", "-f", "wasapi", "-i", "dummy"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    output = proc.stderr or proc.stdout or ""
    return [d for d in parse_audio_devices(output) if d.kind == "audio"]


def _to_stereo(data: np.ndarray) -> np.ndarray:
    """Convert mono audio to stereo by duplicating the channel."""
    if data.ndim == 1:
        return np.column_stack((data, data))
    if data.shape[1] == 1:
        return np.repeat(data, 2, axis=1)
    return data


def _resample(data: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    """Resample audio to target sample rate."""
    if orig_sr == target_sr:
        return data
    num_samples = int(len(data) * target_sr / orig_sr)
    return signal.resample(data, num_samples)


def _normalize(data: np.ndarray) -> np.ndarray:
    """Normalize audio to use full dynamic range without clipping."""
    peak = np.max(np.abs(data))
    if peak > 0 and peak < 0.99:
        data = data * (0.99 / peak)
    return np.clip(data, -1.0, 1.0)


def mix_audio(system_path: Path, mic_path: Path, output_path: Path) -> None:
    """Mix two WAV files into one using scipy for proper resampling."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    system_data, system_sr = sf.read(system_path, dtype=np.float32)
    mic_data, mic_sr = sf.read(mic_path, dtype=np.float32)

    # Convert to stereo
    system_data = _to_stereo(system_data)
    mic_data = _to_stereo(mic_data)

    # Resample to common output rate
    system_data = _resample(system_data, system_sr, OUTPUT_SAMPLE_RATE)
    mic_data = _resample(mic_data, mic_sr, OUTPUT_SAMPLE_RATE)

    # Pad to longest length instead of trimming
    max_len = max(len(system_data), len(mic_data))
    if len(system_data) < max_len:
        pad = np.zeros((max_len - len(system_data), OUTPUT_CHANNELS), dtype=np.float32)
        system_data = np.concatenate([system_data, pad], axis=0)
    if len(mic_data) < max_len:
        pad = np.zeros((max_len - len(mic_data), OUTPUT_CHANNELS), dtype=np.float32)
        mic_data = np.concatenate([mic_data, pad], axis=0)

    # Mix with slight mic boost (speech often quieter than system audio)
    mixed = system_data * 0.8 + mic_data * 1.2
    mixed = mixed / max(1.0, np.max(np.abs(mixed)))
    mixed = _normalize(mixed)

    sf.write(output_path, mixed, OUTPUT_SAMPLE_RATE)
