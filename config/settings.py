"""Environment-backed application configuration."""
from dataclasses import dataclass
from pathlib import Path
import os

@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime settings with no secret values persisted to disk."""
    data_dir: Path = Path("data")
    report_dir: Path = Path("reports")
    log_dir: Path = Path("logs")
    league_id: int = 71
    prediction_token: str | None = os.getenv("TELEGRAM_PREDICTION_BOT_TOKEN")
    prediction_chat_id: str | None = os.getenv("TELEGRAM_PREDICTION_CHAT_ID")
    report_token: str | None = os.getenv("TELEGRAM_REPORT_BOT_TOKEN")
    report_chat_id: str | None = os.getenv("TELEGRAM_REPORT_CHAT_ID")

    def ensure_directories(self) -> None:
        """Create required local runtime directories."""
        for directory in (self.data_dir, self.report_dir, self.log_dir):
            directory.mkdir(parents=True, exist_ok=True)
