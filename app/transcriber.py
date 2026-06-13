import requests
from pathlib import Path


class Transcriber:
    def __init__(self, api_key: str, base_url: str, model: str = "whisper-1"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def transcribe(self, audio_path: Path) -> str:
        url = f"{self.base_url}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {
            "model": self.model,
            "response_format": "json",
        }
        with open(audio_path, "rb") as f:
            files = {"file": (audio_path.name, f, "audio/wav")}
            response = requests.post(url, headers=headers, files=files, data=data, timeout=120)

        if response.status_code == 401:
            raise RuntimeError("API Key 无效或已过期")
        response.raise_for_status()

        result = response.json()
        text = result.get("text", "").strip()
        if not text:
            raise RuntimeError("转录结果为空")
        return text
