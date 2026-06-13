import json
import os
from pathlib import Path


def _load_env_file(path: Path) -> dict:
    """Parse a simple KEY = value .env file."""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class SettingsManager:
    """Read and write user configuration to config.json."""

    def __init__(self, path: str | None = None):
        self.path = Path(path) if path else _project_root() / "config.json"
        self.env = _load_env_file(_project_root() / ".env")

    def _defaults(self) -> dict:
        return {
            "api_key": self.env.get("AIHUBMIX", ""),
            "mic_device_name": "",
            "system_device_name": "",
            "output_dir": "recordings",
            "whisper_model": self.env.get("transcribe_model", "whisper-1"),
            "translation_model": self.env.get("translate_model", "deepseek-v4-flash"),
            "base_url": self.env.get("BASE_URL", "https://aihubmix.com/v1"),
        }

    WHISPER_MODELS = [
        ("whisper-1", "Whisper (默认)"),
        ("whisper-large-v3", "Whisper Large V3 (高精度)"),
    ]

    TRANSLATION_MODELS = [
        ("deepseek-v4-flash", "DeepSeek V4 Flash (推荐)"),
        ("deepseek-v4", "DeepSeek V4 (高精度)"),
        ("gpt-4o-mini", "GPT-4o Mini"),
        ("gpt-4o", "GPT-4o"),
    ]

    def load(self) -> dict:
        defaults = self._defaults()
        if not self.path.exists():
            self.save(defaults)
            return defaults.copy()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
        # Merge with defaults so new keys are always present.
        merged = {**defaults, **data}
        return merged

    def save(self, settings: dict) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
