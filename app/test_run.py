"""Read-only prediction previews and explicit Telegram test delivery."""
from datetime import UTC, datetime, timedelta

from app.models import Prediction
from database.store import JsonStore
from learning.history import forms, merge_results
from prediction.engine import PredictionEngine
from telegram.client import TelegramClient


def _build_future_predictions(settings, collector, logger, limit=4, days=None):
    store = JsonStore(settings.data_dir)
    history = merge_results(store.read("results", []), collector.results(settings.league_id))
    records = store.read("performance", [])
    now = datetime.now(UTC)
    predictions = []

    for fixture in sorted(collector.fixtures(settings.league_id), key=lambda f: f.start):
        if fixture.start <= now:
            continue
        if days is not None and fixture.start > now + timedelta(days=days):
            continue
        home, away = forms(history, fixture.home, fixture.away, now)
        prediction = PredictionEngine(records).predict(fixture, home, away, as_of=now)
        predictions.append(prediction)
        logger.info(
            "PREVIEW fixture=%s outcome=%s probability=%.2f quality=%.2f",
            prediction.fixture, prediction.winner, prediction.confidence, prediction.data_quality,
        )
        if limit and len(predictions) >= limit:
            break
    return predictions


def run_test(settings, collector, logger):
    predictions = _build_future_predictions(settings, collector, logger, limit=0, days=8)
    logger.info("preview_completed matches=%s; no delivery or performance claims", len(predictions))
    return 0


def send_prediction_test(settings, collector, logger):
    """Send the next four real fixtures without touching persistent prediction state."""
    predictions = _build_future_predictions(settings, collector, logger, limit=4, days=None)
    if not predictions:
        logger.warning("prediction_test_skipped reason=no_future_fixture")
        return 0

    client = TelegramClient(settings.prediction_token, settings.prediction_chat_id)
    if not client.enabled:
        logger.error("prediction_test_failed reason=missing_telegram_credentials")
        return 1

    # This path deliberately bypasses reservation/forecast/delivery JSON files.
    # It is a visual Telegram test only and must never enter AL performance memory.
    sent_images = 0
    for batch in client.prediction_batches(predictions):
        if not client.send_predictions(batch):
            logger.error("prediction_test_failed reason=telegram_delivery")
            return 1
        sent_images += 1

    logger.info(
        "prediction_test_sent matches=%s images=%s persistent_state=unchanged",
        len(predictions), sent_images,
    )
    return 0
