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
        client = TelegramClient(self.settings.prediction_token, self.settings.prediction_chat_id)
        self.logger.info("prediction_started utc=%s threshold=%.1f telegram_enabled=%s token_set=%s chat_id_set=%s",
                         now.isoformat(), self.settings.minimum_probability, client.enabled,
                         bool(client.token), bool(client.chat_id))
        stats = dict(outside_window=0, already_locked=0, build_failed=0, low_data=0,
                     low_probability=0, sent=0, send_failed=0, already_sent=0,
                     expired=0, missing_kickoff=0, delivery_disabled=0)
        history = merge_results(self.store.read("results", []), self.collector.results(self.settings.league_id))
        self.store.write("results", history)
        forecasts = self.store.read("forecasts", [])
        published = self.store.read("predictions", [])
        locked = {str(r["fixture_id"]) for r in forecasts + published}
        count = 0
        fixtures = self.collector.fixtures(self.settings.league_id)
        self.logger.info("prediction_data fixtures=%s historical_results=%s", len(fixtures), len(history))
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
            # Persist every forecast, so selection cannot hide model failures.
            forecasts.append(payload)
            self.store.write("forecasts", forecasts)
            locked.add(str(fixture.id))
            if publishable:
                published.append(prediction.payload())
                self.store.write("predictions", published)
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
        # Reconcile a crash between shadow lock and publication persistence.
        ids = {str(p["fixture_id"]) for p in published}
        for row in forecasts:
            if row.get("publishable") and str(row["fixture_id"]) not in ids:
                published.append({k:v for k,v in row.items() if k != "publishable"})
                ids.add(str(row["fixture_id"]))
        self.store.write("predictions", published)
        delivery = self.store.read("delivery", {})
        if client.enabled:
            for row in published:
                key = str(row["fixture_id"])
                if delivery.get(key):
                    stats["already_sent"] += 1
                    continue
                if not row.get("kickoff"):
                    stats["missing_kickoff"] += 1
                    continue
                from learning.adaptive import timestamp
                if timestamp(row["kickoff"]) <= datetime.now(UTC):
                    stats["expired"] += 1
                    continue
                if client.send_prediction(Prediction(**row)):
                    delivery[key] = datetime.now(UTC).isoformat()
                    self.store.write("delivery", delivery)
                    stats["sent"] += 1
                    self.logger.info("prediction_delivered fixture_id=%s", key)
                else:
                    stats["send_failed"] += 1
                    self.logger.warning("prediction_delivery_failed fixture_id=%s retry=next_run_before_kickoff", key)
        else:
            stats["delivery_disabled"] = 1
            self.logger.warning("telegram_disabled reason=missing_credentials: GitHub Secrets değerlerini kontrol edin.")
        self.logger.info("prediction_summary fixtures=%s new_publishable=%s %s", len(fixtures), count,
                         " ".join(f"{key}={value}" for key, value in stats.items()))
        if stats["sent"] == 0:
            self.logger.info("no_telegram_message: Özet sayaçları gönderilmeme nedenlerini gösterir. "
                             "outside_window=T-15 dışında; already_locked=önceden kaydedilmiş; "
                             "low_data=yetersiz geçmiş; low_probability=eşik altında; "
                             "expired=maç başladı; already_sent=önceden gönderildi; "
                             "delivery_disabled=eksik secret; send_failed=Telegram hatası. "
                             "Bağlantıyı bağımsız sınamak için Telegram connection test işini çalıştırın.")
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

