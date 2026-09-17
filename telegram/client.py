"""Telegram Bot API client."""
from __future__ import annotations
from pathlib import Path
import logging
import requests
from app.models import Prediction

logger = logging.getLogger("superlig_al")


class TelegramClient:
    """Sends messages and documents only when credentials are configured."""

    def __init__(self, token: str | None, chat_id: str | None) -> None:
        self.token = (token or "").strip()
        self.chat_id = (chat_id or "").strip()

    @property
    def enabled(self) -> bool:
        """Whether safe delivery is possible."""
        return bool(self.token and self.chat_id)

    def send_prediction(self, prediction: Prediction) -> bool:
        """Send a locked prediction, returning false for an unconfigured bot."""
        note = f"\nNot: {prediction.note}" if prediction.note else ""
        text = (
            f"⚽ {prediction.fixture}\nKazanan: {prediction.winner}\n"
            f"Tahmini skor: {prediction.home_goals}-{prediction.away_goals}\n"
            f"Güven: %{prediction.confidence:.1f}{note}"
        )
        return self.send_text(text)

    def send_text(self, text: str) -> bool:
        """Send an arbitrary text message (used by test mode and reports)."""
        return self._post("sendMessage", {"text": text})

    def send_photo(self, image: Path, caption: str) -> bool:
        """Send a generated PNG report."""
        if not self.enabled:
            logger.warning("telegram_disabled reason=missing_credentials")
            return False
        with image.open("rb") as handle:
            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/sendPhoto",
                data={"chat_id": self.chat_id, "caption": caption},
                files={"photo": handle},
                timeout=30,
            )
        if not response.ok:
            logger.warning(
                "telegram_send_photo_failed status=%s body=%s",
                response.status_code,
                response.text[:500],
            )
        return response.ok

    def _post(self, method: str, payload: dict[str, str]) -> bool:
        if not self.enabled:
            logger.warning("telegram_disabled reason=missing_credentials method=%s", method)
            return False
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.token}/{method}",
                data={"chat_id": self.chat_id, **payload},
                timeout=30,
            )
        except requests.RequestException as exc:
            # Request exception strings can contain the bot token in the URL.
            logger.warning("telegram_request_failed method=%s error_type=%s", method, type(exc).__name__)
            return False
        try:
            body = response.json()
        except ValueError:
            logger.warning("telegram_send_failed method=%s status=%s reason=invalid_json", method, response.status_code)
            return False
        if not response.ok or not isinstance(body, dict) or body.get("ok") is not True:
            code = body.get("error_code", response.status_code) if isinstance(body, dict) else response.status_code
            reason = {400: "invalid_chat_id_or_request", 401: "invalid_bot_token",
                      403: "bot_blocked_or_missing_chat_permissions", 404: "invalid_bot_endpoint",
                      429: "rate_limited"}.get(code, "telegram_api_error")
            logger.warning(
                "telegram_send_failed method=%s status=%s reason=%s", method, response.status_code, reason,
            )
            return False
        logger.info("telegram_send_success method=%s", method)
        return True
