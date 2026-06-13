import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


class HistoryManager:
    """Manage recording history with CRUD operations."""

    def __init__(self, path: str | None = None):
        self.path = Path(path) if path else _project_root() / "history.json"
        self._ensure_file()

    def _ensure_file(self):
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.save([])

    def load(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def save(self, data: list[dict]) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add(self, entry: dict) -> int:
        """Add a new history entry. Returns the new entry ID."""
        data = self.load()
        # Generate new ID
        max_id = max([e.get("id", 0) for e in data], default=0)
        entry["id"] = max_id + 1
        entry["created_at"] = datetime.now().isoformat()
        data.append(entry)
        self.save(data)
        return entry["id"]

    def get(self, entry_id: int) -> Optional[dict]:
        """Get a history entry by ID."""
        data = self.load()
        for entry in data:
            if entry.get("id") == entry_id:
                return entry
        return None

    def update(self, entry_id: int, updates: dict) -> bool:
        """Update a history entry. Returns True if successful."""
        data = self.load()
        for i, entry in enumerate(data):
            if entry.get("id") == entry_id:
                updates["updated_at"] = datetime.now().isoformat()
                data[i] = {**entry, **updates}
                self.save(data)
                return True
        return False

    def delete(self, entry_id: int) -> bool:
        """Delete a history entry. Returns True if successful."""
        data = self.load()
        original_len = len(data)
        data = [e for e in data if e.get("id") != entry_id]
        if len(data) < original_len:
            self.save(data)
            return True
        return False

    def list_all(self, limit: int = 100) -> list[dict]:
        """List all history entries, most recent first."""
        data = self.load()
        data.sort(key=lambda x: x.get("created_at", ""), reverse=True)
        return data[:limit]

    def search(self, query: str) -> list[dict]:
        """Search history by transcription or translation text."""
        data = self.load()
        query_lower = query.lower()
        results = []
        for entry in data:
            transcription = entry.get("transcription", "").lower()
            translation = entry.get("translation", "").lower()
            if query_lower in transcription or query_lower in translation:
                results.append(entry)
        return results