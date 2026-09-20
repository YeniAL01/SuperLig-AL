"""Telegram Bot API client."""

from __future__ import annotations

from pathlib import Path
import logging
from tempfile import TemporaryDirectory

import requests

from app.models import Prediction


logger = logging.getLogger(
    "superlig_al"
)


class TelegramClient:
    """Sends messages and documents only when credentials are configured."""

    def __init__(
        self,
        token: str | None,
        chat_id: str | None,
    ) -> None:
        self.token = (
            token or ""
        ).strip()

        self.chat_id = (
            chat_id or ""
        ).strip()

    @property
    def enabled(self) -> bool:
        """Whether safe delivery is possible."""
        return bool(
            self.token
            and self.chat_id
        )

    def send_prediction(
        self,
        prediction: Prediction,
    ) -> bool:
        """Send one locked final prediction."""
        return self.send_predictions([prediction])

    def prediction_batches(self, predictions: list[Prediction]):
        """Keep image dimensions bounded; a league round fits in one image."""
        for start in range(0, len(predictions), 20):
            yield predictions[start:start + 20]

    def prediction_rows(self, predictions: list[Prediction]):
        rows = []
        for prediction in predictions:
            markets = prediction.markets if isinstance(prediction.markets, dict) else {}
            one_x_two = self._market(markets, "1x2")
            decision = self._format_1x2(prediction, one_x_two).rsplit(" I 📊 Güven:", 1)[0]
            confidence = self._confidence(one_x_two, prediction.confidence)
            rows.append((
                prediction.fixture, decision, f"%{confidence:.1f}",
                self._format_ou25(self._market(markets, "ou25")),
                self._format_btts(self._market(markets, "btts")),
                f"{prediction.home_goals}-{prediction.away_goals}",
                prediction.lineup_verified,
            ))
        return rows

    def send_predictions(self, predictions: list[Prediction]) -> bool:
        """Render and send all ready matches in a single table image."""
        if not predictions:
            return True
        if not self.enabled:
            return False
        from reporting.prediction_table import create_prediction_table
        try:
            with TemporaryDirectory(prefix="superlig-predictions-") as directory:
                image = create_prediction_table(
                    self.prediction_rows(predictions), Path(directory) / "predictions.png"
                )
                return self.send_photo(image, "Süper Lig maç tahminleri")
        except (OSError, ValueError):
            logger.exception("prediction_table_failed")
            return False

    def format_prediction(self, prediction: Prediction) -> str:
        """Render one match without sending it."""
        markets = (
            prediction.markets
            if isinstance(
                prediction.markets,
                dict,
            )
            else {}
        )

        one_x_two = self._market(
            markets,
            "1x2",
        )

        ou25 = self._market(
            markets,
            "ou25",
        )

        btts = self._market(
            markets,
            "btts",
        )

        one_x_two_text = (
            self._format_1x2(
                prediction,
                one_x_two,
            )
        )

        ou25_text = (
            self._format_ou25(
                ou25
            )
        )

        btts_text = (
            self._format_btts(
                btts
            )
        )

        lineup_text = (
            "Doğrulandı" if prediction.lineup_verified else "Doğrulanmadı"
        )
        return (
            f"⚽ {prediction.fixture}\n\n"
            f"🏆 Maç sonucu: {one_x_two_text}\n\n"
            f"🥅 Gol tahmini: {ou25_text} I "
            f"⚔️ Karşılıklı gol: {btts_text}\n\n"
            f"🎯 Tahmini skor: {prediction.home_goals}-{prediction.away_goals} I "
            f"👥 İlk 11: {lineup_text}"
        )

    @staticmethod
    def _market(
        markets: dict,
        name: str,
    ) -> dict:
        value = markets.get(
            name,
            {},
        )

        return (
            value
            if isinstance(
                value,
                dict,
            )
            else {}
        )

    @staticmethod
    def _confidence(
        market: dict,
        fallback: float = 0.0,
    ) -> float:
        try:
            value = float(
                market.get(
                    "confidence",
                    fallback,
                )
            )
        except (
            TypeError,
            ValueError,
        ):
            value = fallback

        return max(
            0.0,
            min(
                100.0,
                value,
            ),
        )

    def _format_1x2(
        self,
        prediction: Prediction,
        market: dict,
    ) -> str:
        selection = str(
            market.get(
                "selection",
                prediction.outcome,
            )
        ).upper()

        confidence = (
            self._confidence(
                market,
                prediction.confidence,
            )
        )

        if selection == "HOME":
            decision = (
                f"{prediction.home_team} Kazanır"
                if prediction.home_team
                else prediction.winner
            )

        elif selection == "AWAY":
            decision = (
                f"{prediction.away_team} Kazanır"
                if prediction.away_team
                else prediction.winner
            )

        elif selection == "DRAW":
            decision = "Beraberlik"

        else:
            decision = (
                prediction.winner
                or "1X2"
            )

        return (
            f"{decision} I 📊 Güven: %{confidence:.1f}"
        )

    def _format_ou25(
        self,
        market: dict,
    ) -> str:
        selection = str(
            market.get(
                "selection",
                "",
            )
        ).upper()

        confidence = (
            self._confidence(
                market
            )
        )

        if selection == "OVER":
            decision = "2,5 Üst"

        elif selection == "UNDER":
            decision = "2,5 Alt"

        else:
            decision = "2,5 Alt/Üst"

        return (
            f"{decision} "
            f"(%{confidence:.1f})"
        )

    def _format_btts(
        self,
        market: dict,
    ) -> str:
        selection = str(
            market.get(
                "selection",
                "",
            )
        ).upper()

        confidence = (
            self._confidence(
                market
            )
        )

        if selection == "YES":
            decision = "Var"

        elif selection == "NO":
            decision = "Yok"

        else:
            decision = "Var/Yok"

        return (
            f"{decision} "
            f"(%{confidence:.1f})"
        )

    def send_text(
        self,
        text: str,
    ) -> bool:
        """Send arbitrary text used by predictions, tests and reports."""
        return self._post(
            "sendMessage",
            {
                "text": text,
            },
        )

    def send_photo(
        self,
        image: Path,
        caption: str,
    ) -> bool:
        """Send a generated PNG report."""
        if not self.enabled:
            logger.warning(
                "telegram_disabled "
                "reason=missing_credentials"
            )
            return False

        try:
            with image.open(
                "rb"
            ) as handle:
                response = requests.post(
                    (
                        "https://api.telegram.org/"
                        f"bot{self.token}/sendPhoto"
                    ),
                    data={
                        "chat_id":
                            self.chat_id,
                        "caption":
                            caption,
                    },
                    files={
                        "photo":
                            handle,
                    },
                    timeout=30,
                )

        except (
            OSError,
            requests.RequestException,
        ) as exc:
            logger.warning(
                "telegram_send_photo_failed "
                "error_type=%s",
                type(exc).__name__,
            )
            return False

        try:
            body = response.json()
        except ValueError:
            return False
        return response.ok and isinstance(body, dict) and body.get("ok") is True

    def _post(
        self,
        method: str,
        payload: dict[str, str],
    ) -> bool:
        if not self.enabled:
            logger.warning(
                "telegram_disabled "
                "reason=missing_credentials "
                "method=%s",
                method,
            )
            return False

        try:
            response = requests.post(
                (
                    "https://api.telegram.org/"
                    f"bot{self.token}/{method}"
                ),
                data={
                    "chat_id":
                        self.chat_id,
                    **payload,
                },
                timeout=30,
            )

        except requests.RequestException as exc:
            # Request exception strings can contain the bot token in
            # the request URL. Log only the exception type.
            logger.warning(
                "telegram_request_failed "
                "method=%s "
                "error_type=%s",
                method,
                type(exc).__name__,
            )
            return False

        try:
            body = response.json()

        except ValueError:
            logger.warning(
                "telegram_send_failed "
                "method=%s "
                "status=%s "
                "reason=invalid_json",
                method,
                response.status_code,
            )
            return False

        if (
            not response.ok
            or not isinstance(
                body,
                dict,
            )
            or body.get(
                "ok"
            )
            is not True
        ):
            code = (
                body.get(
                    "error_code",
                    response.status_code,
                )
                if isinstance(
                    body,
                    dict,
                )
                else response.status_code
            )

            reason = {
                400:
                    "invalid_chat_id_or_request",
                401:
                    "invalid_bot_token",
                403:
                    "bot_blocked_or_missing_chat_permissions",
                404:
                    "invalid_bot_endpoint",
                429:
                    "rate_limited",
            }.get(
                code,
                "telegram_api_error",
            )

            logger.warning(
                "telegram_send_failed "
                "method=%s "
                "status=%s "
                "reason=%s",
                method,
                response.status_code,
                reason,
            )

            return False

        logger.info(
            "telegram_send_success "
            "method=%s",
            method,
        )

        return True
