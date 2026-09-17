"""Immutable pre-match snapshots and crash-safe Telegram delivery reservations."""
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
        """Build and persist forecasts only. Telegram delivery is a separate phase."""
        now = datetime.now(UTC)
        self.logger.info("prediction_started utc=%s threshold=%.1f", now.isoformat(), self.settings.minimum_probability)
        stats = dict(outside_window=0, already_locked=0, build_failed=0, low_data=0,
                     low_probability=0, eligible=0)
        conflicts = self.store.read("result_conflicts", [])
        history = merge_results(self.store.read("results", []),
                                self.collector.results(self.settings.league_id), conflicts)
        self.store.write("results", history)
        self.store.write("result_conflicts", conflicts)
        forecasts = self.store.read("forecasts", [])
        published = self.store.read("predictions", [])
        locked = {str(r["fixture_id"]) for r in forecasts + published}
        count = 0
        fixtures = self.collector.fixtures(self.settings.league_id)
        self.logger.info("prediction_data fixtures=%s historical_results=%s conflicts=%s",
                         len(fixtures), len(history), len(conflicts))
        if fixtures:
            nearest = min(fixtures, key=lambda f: f.start)
            self.logger.info("next_fixture fixture=%s - %s kickoff_utc=%s minutes_to_kickoff=%.1f",
                             nearest.home, nearest.away, nearest.start.isoformat(),
                             (nearest.start-now).total_seconds()/60)
        for fixture in fixtures:
            minutes = (fixture.start-datetime.now(UTC)).total_seconds()/60
            if str(fixture.id) in locked:
                stats["already_locked"] += 1
                continue
            if not 0 < minutes <= 15:
                stats["outside_window"] += 1
                continue
            prediction = self._build(fixture)
            if prediction is None:
                stats["build_failed"] += 1
                self.logger.info("prediction_skipped fixture_id=%s reason=kickoff_reached_during_build", fixture.id)
                continue
            payload = prediction.payload()
            publishable = (prediction.data_quality >= .5 and
                           prediction.confidence >= self.settings.minimum_probability)
            payload["publishable"] = publishable
            forecasts.append(payload)
            self.store.write("forecasts", forecasts)
            locked.add(str(fixture.id))
            if publishable:
                published.append(prediction.payload())
                self.store.write("predictions", published)
                stats["eligible"] += 1
                count += 1
            else:
                reasons = []
                if prediction.data_quality < .5:
                    stats["low_data"] += 1
                    reasons.append("insufficient_history_min_5_per_team")
                if prediction.confidence < self.settings.minimum_probability:
                    stats["low_probability"] += 1
                    reasons.append("probability_below_threshold")
                self.logger.info("shadow_only fixture_id=%s probability=%.2f threshold=%.2f quality=%.2f reasons=%s",
                                 fixture.id, prediction.confidence, self.settings.minimum_probability,
                                 prediction.data_quality, ",".join(reasons))

        ids = {str(p["fixture_id"]) for p in published}
        for row in forecasts:
            if row.get("publishable") and str(row["fixture_id"]) not in ids:
                published.append({k:v for k,v in row.items() if k != "publishable"})
                ids.add(str(row["fixture_id"]))
        self.store.write("predictions", published)
        self._reserve_delivery(published)
        self.logger.info("prediction_summary fixtures=%s new_eligible=%s %s", len(fixtures), count,
                         " ".join(f"{key}={value}" for key, value in stats.items()))
        return count

    def _reserve_delivery(self, published: list) -> int:
        """Reserve eligible messages before the workflow commits/pushes state."""
        from learning.adaptive import timestamp
        delivery = self.store.read("delivery", {})
        reserved = 0
        now = datetime.now(UTC)
        for row in published:
            key = str(row["fixture_id"])
            state = delivery.get(key)
            # Legacy string values mean the message was already delivered.
            if isinstance(state, str) or (isinstance(state, dict) and state.get("status") in {"attempting", "delivered"}):
                continue
            if not row.get("kickoff") or timestamp(row["kickoff"]) <= now:
                continue
            delivery[key] = {"status": "attempting", "reserved_at": now.isoformat()}
            reserved += 1
        self.store.write("delivery", delivery)
        self.logger.info("delivery_reserved count=%s; Telegram must run only after this state is pushed", reserved)
        return reserved

    def deliver(self) -> int:
        """Send only pre-persisted reservations. Return non-zero on any delivery failure."""
        from learning.adaptive import timestamp
        client = TelegramClient(self.settings.prediction_token, self.settings.prediction_chat_id)
        delivery = self.store.read("delivery", {})
        predictions = {str(p["fixture_id"]): p for p in self.store.read("predictions", [])}
        failures = 0
        sent = 0
        now = datetime.now(UTC)
        if not client.enabled:
            pending = [k for k, v in delivery.items() if isinstance(v, dict) and v.get("status") == "attempting"]
            if pending:
                self.logger.error("telegram_disabled pending=%s reason=missing_credentials", len(pending))
                return 1
            return 0
        for key, state in list(delivery.items()):
            if not isinstance(state, dict) or state.get("status") != "attempting":
                continue
            row = predictions.get(str(key))
            if not row:
                failures += 1
                self.logger.error("prediction_delivery_failed fixture_id=%s reason=missing_persisted_prediction", key)
                continue
            if not row.get("kickoff") or timestamp(row["kickoff"]) <= now:
                delivery[key] = {**state, "status": "expired", "updated_at": datetime.now(UTC).isoformat()}
                failures += 1
                continue
            if client.send_prediction(Prediction(**row)):
                delivery[key] = {**state, "status": "delivered", "delivered_at": datetime.now(UTC).isoformat()}
                sent += 1
                self.logger.info("prediction_delivered fixture_id=%s", key)
            else:
                delivery[key] = {**state, "status": "failed", "failed_at": datetime.now(UTC).isoformat()}
                failures += 1
                self.logger.error("prediction_delivery_failed fixture_id=%s", key)
        self.store.write("delivery", delivery)
        self.logger.info("delivery_summary sent=%s failed=%s", sent, failures)
        return 1 if failures else 0

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
