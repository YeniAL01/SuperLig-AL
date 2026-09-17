"""Atomic JSON persistence behind a small repository interface."""
from __future__ import annotations
from pathlib import Path
from typing import Any
import json
import tempfile

class JsonStore:
    """Persists named JSON documents atomically; replaceable with SQLite later."""
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def read(self, name: str, default: Any) -> Any:
        """Return document content or a caller-supplied default."""
        path = self.directory / f"{name}.json"
        if not path.exists():
            return default
        # Corruption must stop the run rather than silently erase learning history.
        return json.loads(path.read_text(encoding="utf-8-sig"))

    def write(self, name: str, value: Any) -> None:
        """Atomically replace a named document."""
        target = self.directory / f"{name}.json"
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.directory, delete=False) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        temporary.replace(target)
