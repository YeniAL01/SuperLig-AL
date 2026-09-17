"""SuperLig-AL CLI. Successful jobs exit zero unless an action fails."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

from app.service import PredictionService
from collectors.fotmob import FotMobCollector
from config.settings import Settings
from database.store import JsonStore
from learning.adaptive import (
    build_learning_samples,
    model_weights,
    update_learning_state,
)
from learning.history import merge_results
from learning.performance import (
    score_prediction,
    summarize,
)
from memory.engine import update_memory
from utils.logging import configure_logging


def learn(settings, collector):
    """Settle forecasts and update persistent learning state."""
    logger = configure_logging(settings)
    store = JsonStore(settings.data_dir)

    # --------------------------------------------------------------
    # 1. Refresh settled results safely.
    # Provider corrections are recorded separately and never stop the
    # complete learning/prediction workflow.
    # --------------------------------------------------------------
    conflicts = store.read(
        "result_conflicts",
        [],
    )

    results = merge_results(
        store.read(
            "results",
            [],
        ),
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

    by_id = {
        str(row["fixture_id"]): row
        for row in results
    }

    forecasts = store.read(
        "forecasts",
        [],
    )

    delivery = store.read(
        "delivery",
        {},
    )

    records = store.read(
        "performance",
        [],
    )

    settled = {
        str(row["fixture_id"])
        for row in records
    }

    added = 0

    # --------------------------------------------------------------
    # 2. Settle forecasts that now have final match results.
    # --------------------------------------------------------------
    for prediction in forecasts:
        key = str(
            prediction["fixture_id"]
        )

        if key in settled:
            continue

        actual = by_id.get(key)

        if (
            actual
            and prediction.get(
                "home_team"
            )
            and (
                actual["home_team"]
                != prediction["home_team"]
                or actual["away_team"]
                != prediction["away_team"]
            )
        ):
            logger.warning(
                "settlement_skipped "
                "fixture_id=%s "
                "reason=team_mismatch",
                key,
            )
            continue

        # A fixture can occasionally be missing from the bulk result
        # response. In that case, try its match-detail endpoint.
        if actual is None:
            try:
                detail = collector.match(
                    int(key)
                )

                header = detail.get(
                    "header",
                    {},
                )

                score = _final_score(
                    header.get(
                        "teams",
                        [],
                    )
                )

                if (
                    not header.get(
                        "status",
                        {},
                    ).get(
                        "finished"
                    )
                    or score is None
                ):
                    continue

                actual = {
                    "home_goals":
                        score[0],
                    "away_goals":
                        score[1],
                    "available_at":
                        datetime.now(
                            UTC
                        ).isoformat(),
                }

            except Exception as exc:
                logger.warning(
                    "settlement_failed "
                    "fixture_id=%s "
                    "error=%s",
                    key,
                    type(exc).__name__,
                )
                continue

        delivery_state = delivery.get(
            key
        )

        # Legacy string delivery values mean that the prediction was
        # already successfully delivered.
        delivered = (
            isinstance(
                delivery_state,
                str,
            )
            or (
                isinstance(
                    delivery_state,
                    dict,
                )
                and delivery_state.get(
                    "status"
                )
                == "delivered"
            )
        )

        scored = score_prediction(
            prediction,
            actual["home_goals"],
            actual["away_goals"],
        )

        record = {
            **prediction,
            **scored,
            "eligible": bool(
                prediction.get(
                    "publishable"
                )
            ),
            "delivered": delivered,
            "actual_home":
                actual["home_goals"],
            "actual_away":
                actual["away_goals"],
            "settled_at":
                actual.get(
                    "available_at",
                    datetime.now(
                        UTC
                    ).isoformat(),
                ),
        }

        records.append(
            record
        )

        settled.add(key)
        added += 1

    store.write(
        "performance",
        records,
    )

    # --------------------------------------------------------------
    # 3. Rebuild memory from immutable settled performance records.
    # --------------------------------------------------------------
    memory = {}

    for row in records:
        memory = update_memory(
            memory,
            row,
        )

    store.write(
        "memory",
        memory,
    )

    # --------------------------------------------------------------
    # 4. Keep the existing performance metrics.
    # Eligible and actually delivered forecasts remain separate.
    # --------------------------------------------------------------
    metrics = summarize(
        records
    )

    store.write(
        "metrics",
        metrics,
    )

    # --------------------------------------------------------------
    # 5. Keep the existing adaptive-v2 expert model state.
    # --------------------------------------------------------------
    model_state = {
        "version": "adaptive-v2",
        "settled_matches":
            len(records),
        "weights": model_weights(
            records,
            [
                "poisson",
                "elo",
                "baseline",
            ],
            datetime.now(UTC),
        ),
    }

    store.write(
        "model_state",
        model_state,
    )

    # --------------------------------------------------------------
    # 6. Build market-level learning samples.
    # --------------------------------------------------------------
    learning_samples = (
        build_learning_samples(
            records,
            results,
            delivered_only=False,
        )
    )

    previous_learning_state = (
        store.read(
            "learning_state",
            {},
        )
    )

    learning_state, events = (
        update_learning_state(
            previous_learning_state,
            learning_samples,
            now=datetime.now(UTC),
        )
    )

    store.write(
        "learning_state",
        learning_state,
    )

    # --------------------------------------------------------------
    # 7. Log learning status without Telegram or AI calls.
    # --------------------------------------------------------------
    market_status = {}

    for market, state in (
        learning_state.get(
            "markets",
            {}
        ).items()
    ):
        market_status[market] = {
            "status":
                state.get(
                    "status"
                ),
            "samples":
                state.get(
                    "total_samples",
                    0,
                ),
            "accuracy":
                state.get(
                    "season_accuracy"
                ),
        }

    logger.info(
        "adaptive_learning "
        "samples=%s "
        "events=%s "
        "markets=%s",
        len(learning_samples),
        len(events),
        json.dumps(
            market_status,
            ensure_ascii=False,
        ),
    )

    for event in events:
        logger.info(
            "adaptive_learning_event "
            "market=%s "
            "type=%s "
            "reason=%s",
            event.get(
                "market"
            ),
            event.get(
                "type"
            ),
            event.get(
                "reason"
            ),
        )

    logger.info(
        "learning_completed "
        "settled=%s "
        "total_performance=%s "
        "learning_samples=%s "
        "conflicts=%s",
        added,
        len(records),
        len(learning_samples),
        len(conflicts),
    )

    return added


def _final_score(teams):
    """Extract a valid final score from the provider match header."""
    if isinstance(
        teams,
        dict,
    ):
        teams = [
            teams.get(
                "home",
                {},
            ),
            teams.get(
                "away",
                {},
            ),
        ]

    if (
        isinstance(
            teams,
            list,
        )
        and len(teams) == 2
        and all(
            isinstance(
                team,
                dict,
            )
            and team.get(
                "score"
            )
            is not None
            for team in teams
        )
    ):
        scores = tuple(
            int(
                team["score"]
            )
            for team in teams
        )

        return (
            scores
            if min(scores) >= 0
            else None
        )

    return None


def main():
    parser = argparse.ArgumentParser(
        description="SuperLig-AL"
    )

    parser.add_argument(
        "command",
        choices=(
            "predict",
            "deliver",
            "learn",
            "test",
            "test-telegram",
            "backtest",
            "import-history",
            "metrics",
        ),
    )

    parser.add_argument(
        "--csv",
        type=Path,
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=Path(
            "reports/backtest.json"
        ),
    )

    args = parser.parse_args()

    settings = Settings()

    # --------------------------------------------------------------
    # Telegram connectivity test
    # --------------------------------------------------------------
    if (
        args.command
        == "test-telegram"
    ):
        from telegram.client import (
            TelegramClient,
        )

        logger = configure_logging(
            settings
        )

        client = TelegramClient(
            settings.prediction_token,
            settings.prediction_chat_id,
        )

        logger.info(
            "telegram_test_started "
            "token_set=%s "
            "chat_id_set=%s",
            bool(client.token),
            bool(client.chat_id),
        )

        sent = client.send_text(
            "✅ SuperLig-AL Telegram bağlantı testi başarılı.\n"
            "Bu bir bağlantı testidir; maç tahmini değildir."
        )

        if sent:
            logger.info(
                "telegram_test_success: "
                "Test mesajı Telegram API "
                "tarafından kabul edildi."
            )
            return 0

        logger.error(
            "telegram_test_failed: "
            "Bot token/chat ID, botla sohbet "
            "ve kanal izinlerini kontrol edin."
        )

        return 1

    store = JsonStore(
        settings.data_dir
    )

    # --------------------------------------------------------------
    # Backtest / historical import
    # --------------------------------------------------------------
    if args.command in (
        "backtest",
        "import-history",
    ):
        if not args.csv:
            parser.error(
                "--csv is required"
            )

        from learning.backtest import (
            evaluate,
            read_csv,
        )

        rows = read_csv(
            args.csv
        )

        if (
            args.command
            == "import-history"
        ):
            conflicts = store.read(
                "result_conflicts",
                [],
            )

            merged = merge_results(
                store.read(
                    "results",
                    [],
                ),
                rows,
                conflicts,
            )

            store.write(
                "results",
                merged,
            )

            store.write(
                "result_conflicts",
                conflicts,
            )

            print(
                f"Historical matches: "
                f"{len(merged)}"
            )

        else:
            report = evaluate(
                rows,
                settings.minimum_probability,
            )

            args.output.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            args.output.write_text(
                json.dumps(
                    report,
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )

            print(
                json.dumps(
                    {
                        key: value
                        for key, value
                        in report.items()
                        if key != "records"
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )

        return 0

    # --------------------------------------------------------------
    # Metrics
    # --------------------------------------------------------------
    if args.command == "metrics":
        print(
            json.dumps(
                summarize(
                    store.read(
                        "performance",
                        [],
                    )
                ),
                ensure_ascii=False,
                indent=2,
            )
        )

        return 0

    logger = configure_logging(
        settings
    )

    collector = FotMobCollector()

    # --------------------------------------------------------------
    # Runtime commands
    # --------------------------------------------------------------
    if args.command == "predict":
        PredictionService(
            settings,
            collector,
            logger,
        ).run()

    elif args.command == "deliver":
        return PredictionService(
            settings,
            collector,
            logger,
        ).deliver()

    elif args.command == "learn":
        learn(
            settings,
            collector,
        )

    else:
        from app.test_run import (
            run_test,
        )

        run_test(
            settings,
            collector,
            logger,
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
