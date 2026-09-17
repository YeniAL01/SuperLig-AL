"""Immutable pre-match snapshots, including non-published shadow forecasts."""
from datetime import UTC, datetime
import logging
from app.models import Prediction
from database.store import JsonStore
from prediction.engine import PredictionEngine
from learning.history import forms, merge_results
from telegram.client import TelegramClient

class PredictionService:
    def __init__(self, settings, collector, logger: logging.Logger):
        self.settings, self.collector, self.logger = settings, collector, logger
        self.store = JsonStore(settings.data_dir)

    def run(self) -> int:
        now = datetime.now(UTC)
        history = merge_results(self.store.read("results", []), self.collector.results(self.settings.league_id))
        self.store.write("results", history)
        forecasts = self.store.read("forecasts", [])
        published = self.store.read("predictions", [])
        locked = {str(r["fixture_id"]) for r in forecasts + published}
        count = 0
        for fixture in self.collector.fixtures(self.settings.league_id):
            minutes = (fixture.start-datetime.now(UTC)).total_seconds()/60
            if str(fixture.id) in locked or not 0 < minutes <= 15:
                continue
            prediction = self._build(fixture)
            if prediction is None:
                continue
            payload = prediction.payload()
            publishable = (prediction.data_quality >= .5 and
                           prediction.confidence >= self.settings.minimum_probability)
            payload["publishable"] = publishable
            # Persist every forecast, so selection cannot hide model failures.
            forecasts.append(payload)
            self.store.write("forecasts", forecasts)
            locked.add(str(fixture.id))
            if publishable:
                published.append(prediction.payload())
                self.store.write("predictions", published)
                count += 1
            else:
                self.logger.info("shadow_only fixture_id=%s probability=%s quality=%s",
                                 fixture.id, prediction.confidence, prediction.data_quality)
        # Reconcile a crash between shadow lock and publication persistence.
        ids = {str(p["fixture_id"]) for p in published}
        for row in forecasts:
            if row.get("publishable") and str(row["fixture_id"]) not in ids:
                published.append({k:v for k,v in row.items() if k != "publishable"})
                ids.add(str(row["fixture_id"]))
        self.store.write("predictions", published)
        delivery = self.store.read("delivery", {})
        client = TelegramClient(self.settings.prediction_token, self.settings.prediction_chat_id)
        if client.enabled:
            for row in published:
                key = str(row["fixture_id"])
                if delivery.get(key) or not row.get("kickoff"):
                    continue
                from learning.adaptive import timestamp
                if timestamp(row["kickoff"]) <= datetime.now(UTC):
                    continue
                if client.send_prediction(Prediction(**row)):
                    delivery[key] = datetime.now(UTC).isoformat()
                    self.store.write("delivery", delivery)
        return count

    def _build(self, fixture):
        as_of = datetime.now(UTC)
        home, away = forms(self.store.read("results", []), fixture.home, fixture.away, as_of)
        verified = False
        try:
            verified = self._lineup_verified(self.collector.match(fixture.id))
        except Exception as exc:
            self.logger.warning("lineup_unavailable fixture_id=%s error=%s", fixture.id, type(exc).__name__)
        if datetime.now(UTC) >= fixture.start:
            return None
        return PredictionEngine(self.store.read("performance", [])).predict(
            fixture, home, away, lineup_verified=verified, as_of=as_of)

    @staticmethod
    def _lineup_verified(detail):
        lineup = detail.get("content", {}).get("lineup", {})
        if not isinstance(lineup, dict):
            return False
        return all(isinstance(lineup.get(side), dict) and
                   len(lineup[side].get("starters") or []) == 11 for side in ("homeTeam", "awayTeam"))

