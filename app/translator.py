import requests


class Translator:
    def __init__(self, api_key: str, base_url: str, model: str = "gpt-4o-mini"):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model

    def translate_to_chinese(self, text: str) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "你是专业翻译。请把用户提供的转录文本翻译成自然流畅的中文，保留专有名词。",
                },
                {"role": "user", "content": text},
            ],
        }
        response = requests.post(url, headers=headers, json=payload, timeout=120)

        if response.status_code == 401:
            raise RuntimeError("API Key 无效或已过期")
        response.raise_for_status()

        result = response.json()
        choices = result.get("choices", [])
        if not choices:
            raise RuntimeError("翻译结果为空")
        return choices[0]["message"]["content"].strip()
