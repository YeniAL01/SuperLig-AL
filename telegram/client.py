"""Telegram Bot API client."""
from pathlib import Path
import requests
from app.models import Prediction

class TelegramClient:
    """Sends messages and documents only when credentials are configured."""
    def __init__(self, token: str | None, chat_id: str | None) -> None:
        self.token, self.chat_id = token, chat_id

    @property
    def enabled(self) -> bool:
        """Whether safe delivery is possible."""
        return bool(self.token and self.chat_id)

    def send_prediction(self, prediction: Prediction) -> bool:
        """Send a locked prediction, returning false for an unconfigured bot."""
        note = f"\nNot: {prediction.note}" if prediction.note else ""
        text = (f"⚽ {prediction.fixture}\nKazanan: {prediction.winner}\n"
                f"Tahmini skor: {prediction.home_goals}-{prediction.away_goals}\n"
                f"Güven: %{prediction.confidence:.1f}{note}")
        return self._post("sendMessage", {"text": text})

    def send_photo(self, image: Path, caption: str) -> bool:
        """Send a generated PNG report."""
        if not self.enabled:
            return False
        with image.open("rb") as handle:
            response = requests.post(f"https://api.telegram.org/bot{self.token}/sendPhoto", data={"chat_id": self.chat_id, "caption": caption}, files={"photo": handle}, timeout=30)
        return response.ok

    def _post(self, method: str, payload: dict[str, str]) -> bool:
        if not self.enabled:
            return False
        return requests.post(f"https://api.telegram.org/bot{self.token}/{method}", data={"chat_id": self.chat_id, **payload}, timeout=30).ok
