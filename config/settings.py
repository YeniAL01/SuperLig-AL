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

    # FotMob Süper Lig competition identifier.
    league_id: int = 71

    # Minimum calibrated 1X2 confidence required before a forecast is
    # eligible for Telegram delivery.
    minimum_probability: float = 58.0

    # Prediction Telegram bot.
    prediction_token: str | None = os.getenv(
        "TELEGRAM_PREDICTION_BOT_TOKEN"
    )

    prediction_chat_id: str | None = os.getenv(
        "TELEGRAM_PREDICTION_CHAT_ID"
    )

    # Weekly/performance report Telegram bot.
    report_token: str | None = os.getenv(
        "TELEGRAM_REPORT_BOT_TOKEN"
    )

    report_chat_id: str | None = os.getenv(
        "TELEGRAM_REPORT_CHAT_ID"
    )

    def ensure_directories(
        self,
    ) -> None:
        """Create required local runtime directories."""
        for directory in (
            self.data_dir,
            self.report_dir,
            self.log_dir,
        ):
            directory.mkdir(
                parents=True,
                exist_ok=True,
            )
