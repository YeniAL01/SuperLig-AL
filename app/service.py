"""Prediction workflow coordinator."""
from __future__ import annotations
from datetime import UTC, datetime, timedelta
import logging
from app.models import Fixture, Prediction
from ai.decision import decide
from collectors.fotmob import FotMobCollector
from config.settings import Settings
from database.store import JsonStore
from prediction.confidence import ConfidenceEngine
from prediction.engine import PredictionEngine, TeamForm
from telegram.client import TelegramClient

class PredictionService:
    """Coordinates collection, decision, immutable lock, and delivery."""
    def __init__(self, settings: Settings, collector: FotMobCollector, logger: logging.Logger) -> None:
        self.settings, self.collector, self.logger = settings, collector, logger
        self.store = JsonStore(settings.data_dir)
        self.confidence = ConfidenceEngine()

    def run(self) -> int:
        """Inspect fixtures and publish only those in the T-15 lock window."""
        published = self.store.read("predictions", [])
        published_ids = {int(p["fixture_id"]) for p in published}
        snapshots = self.store.read("pre_match_analysis", {})
        fallbacks = self.store.read("fallback_predictions", {})
        count = 0
        for fixture in self.collector.fixtures(self.settings.league_id):
            minutes = (fixture.start - datetime.now(UTC)).total_seconds() / 60
            if 18 <= minutes <= 60:
                snapshots[str(fixture.id)] = {"checked_at": datetime.now(UTC).isoformat(), "minutes_to_kickoff": round(minutes, 1)}
            if 17.5 <= minutes <= 18.5 and str(fixture.id) not in fallbacks:
                fallback = self._build(fixture)
                if fallback is not None:
                    fallbacks[str(fixture.id)] = fallback.payload()
            if fixture.id in published_ids or not 0 <= minutes <= 15:
                continue
            prediction = self._build(fixture) or self._restore(fallbacks.get(str(fixture.id)))
            if prediction is None:
                continue
            decision = decide(prediction.confidence, self.confidence.minimum_to_publish, prediction.lineup_verified, minutes)
            if not decision.publish:
                self.logger.info("prediction_rejected fixture_id=%s reason=%s", fixture.id, decision.reason)
                continue
            published.append(prediction.payload())
            self.store.write("predictions", published)
            TelegramClient(self.settings.prediction_token, self.settings.prediction_chat_id).send_prediction(prediction)
            self.logger.info("prediction_locked fixture_id=%s confidence=%s", fixture.id, prediction.confidence)
            count += 1
        self.store.write("pre_match_analysis", snapshots)
        self.store.write("fallback_predictions", fallbacks)
        return count

    @staticmethod
    def _restore(payload: object) -> Prediction | None:
        """Reconstruct a T-18 fallback prediction after a transient provider outage."""
        return Prediction(**payload) if isinstance(payload, dict) else None

    def _build(self, fixture: Fixture) -> Prediction | None:
        """Collect match detail and make a conservative decision."""
        try:
            detail = self.collector.match(fixture.id)
        except Exception as exc:
            self.logger.warning("match_collection_failed fixture_id=%s error=%s", fixture.id, exc)
            return None
        lineup_verified = self._lineup_verified(detail)
        home, away = self._forms(detail)
        records = self.store.read("performance", [])
        from learning.performance import calibration
        confidence = self.confidence.calculate(home, away, lineup_verified, calibration(records))
        if confidence < self.confidence.minimum_to_publish:
            self.logger.info("prediction_rejected fixture_id=%s confidence=%s", fixture.id, confidence)
            return None
        prediction = PredictionEngine().predict(fixture, home, away, confidence, lineup_verified)
        if not lineup_verified:
            return Prediction(**{**prediction.payload(), "note": "İlk 11 doğrulanamadığı için analiz mevcut veriler kullanılarak oluşturulmuştur."})
        return prediction

    @staticmethod
    def _lineup_verified(detail: dict) -> bool:
        """Recognize a provider's non-empty confirmed lineup list."""
        lineups = detail.get("content", {}).get("lineup", {})
        return bool(lineups.get("homeTeam", {}).get("starters") and lineups.get("awayTeam", {}).get("starters"))

    @staticmethod
    def _forms(detail: dict) -> tuple[TeamForm, TeamForm]:
        """Extract available form rows, retaining conservative defaults."""
        form = detail.get("content", {}).get("form", {})
        def build(side: str) -> TeamForm:
            rows = form.get(side, []) if isinstance(form, dict) else []
            scores = [row.get("score", {}) for row in rows if isinstance(row, dict)]
            scored = sum(float(x.get("home", 0)) + float(x.get("away", 0)) for x in scores) / max(1, len(scores) * 2)
            return TeamForm(scored or 1.0, 1.2, 1.0, len(scores))
        return build("homeTeam"), build("awayTeam")
