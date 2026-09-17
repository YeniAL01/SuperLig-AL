"""SuperLig-AL command line entry point."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime

from app.service import PredictionService
from collectors.fotmob import FotMobCollector
from config.settings import Settings
from database.store import JsonStore
from learning.adaptive import (
    build_learning_samples,
    update_learning_state,
)
from learning.performance import (
    evaluate_predictions,
    summarize,
)
from telegram.client import TelegramClient
from utils.logging import configure_logging


def _settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings


def _collector():
    return FotMobCollector()


def predict() -> int:
    """Run the pre-match timing and prediction service."""
    settings = _settings()
    logger = configure_logging(
        settings
    )

    service = PredictionService(
        settings,
        _collector(),
        logger,
    )

    service.run()

    return 0


def deliver() -> int:
    """Deliver only predictions already reserved on disk."""
    settings = _settings()
    logger = configure_logging(
        settings
    )

    service = PredictionService(
        settings,
        _collector(),
        logger,
    )

    return service.deliver()


def learn() -> int:
    """Settle predictions and update adaptive learning state."""
    settings = _settings()
    logger = configure_logging(
        settings
    )

    store = JsonStore(
        settings.data_dir
    )

    collector = _collector()

    conflicts = store.read(
        "result_conflicts",
        [],
    )

    stored_results = store.read(
        "results",
        [],
    )

    from learning.history import merge_results

    results = merge_results(
        stored_results,
        collector.results(
            settings.league_id
        ),
        conflicts,
    )

    store.write(
        "results",
        results,
    )

    store.write(
        "result_conflicts",
        conflicts,
    )

    predictions = store.read(
        "predictions",
        [],
    )

    delivery = store.read(
        "delivery",
        {},
    )

    # Delivery status belongs to the persisted delivery ledger. Copy the
    # status into the evaluation input without mutating the immutable
    # prediction snapshots.
    evaluation_predictions = []

    for prediction in predictions:
        row = dict(
            prediction
        )

        fixture_id = str(
            row.get(
                "fixture_id",
                "",
            )
        )

        delivery_state = delivery.get(
            fixture_id
        )

        if isinstance(
            delivery_state,
            str,
        ):
            delivered = True

        elif isinstance(
            delivery_state,
            dict,
        ):
            delivered = (
                delivery_state.get(
                    "status"
                )
                == "delivered"
            )

        else:
            delivered = False

        row[
            "delivered"
        ] = delivered

        row[
            "eligible"
        ] = True

        evaluation_predictions.append(
            row
        )

    performance = evaluate_predictions(
        evaluation_predictions,
        results,
    )

    store.write(
        "performance",
        performance,
    )

    learning_samples = build_learning_samples(
        evaluation_predictions,
        results,
        delivered_only=False,
    )

    current_state = store.read(
        "learning_state",
        {},
    )

    learning_state, events = (
        update_learning_state(
            current_state,
            learning_samples,
            now=datetime.now(
                UTC
            ),
        )
    )

    store.write(
        "learning_state",
        learning_state,
    )

    store.write(
        "learning_events",
        events,
    )

    metrics = summarize(
        performance
    )

    store.write(
        "metrics",
        metrics,
    )

    logger.info(
        "learning_completed "
        "predictions=%s "
        "results=%s "
        "settled=%s "
        "samples=%s "
        "events=%s",
        len(
            predictions
        ),
        len(
            results
        ),
        len(
            performance
        ),
        len(
            learning_samples
        ),
        len(
            events
        ),
    )

    return 0


def test_telegram() -> int:
    """Send a simple connection test through the prediction bot."""
    settings = _settings()
    logger = configure_logging(
        settings
    )

    client = TelegramClient(
        settings.prediction_token,
        settings.prediction_chat_id,
    )

    if not client.enabled:
        logger.error(
            "telegram_test_failed "
            "reason=missing_credentials"
        )
        return 1

    sent = client.send_text(
        "✅ SuperLig-AL Telegram bağlantı testi başarılı."
    )

    if not sent:
        logger.error(
            "telegram_test_failed "
            "reason=telegram_api_rejected"
        )
        return 1

    logger.info(
        "telegram_test_success"
    )

    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="SuperLig-AL"
    )

    parser.add_argument(
        "command",
        choices=(
            "predict",
            "deliver",
            "learn",
            "test-telegram",
        ),
    )

    args = parser.parse_args()

    if args.command == "predict":
        return predict()

    if args.command == "deliver":
        return deliver()

    if args.command == "learn":
        return learn()

    if args.command == "test-telegram":
        return test_telegram()

    return 2


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
