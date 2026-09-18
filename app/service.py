"""Immutable pre-match snapshots and crash-safe Telegram delivery reservations."""

from datetime import UTC, datetime
import logging

from app.models import Prediction
from database.store import JsonStore
from learning.history import forms, merge_results
from prediction.engine import PredictionEngine
from telegram.client import TelegramClient


ANALYSIS_WINDOW_MINUTES = 60
LINEUP_CHECK_UNTIL_MINUTES = 30
FINAL_PREDICTION_MINUTES = 15


class PredictionService:
    def __init__(
        self,
        settings,
        collector,
        logger: logging.Logger,
    ):
        self.settings = settings
        self.collector = collector
        self.logger = logger
        self.store = JsonStore(
            settings.data_dir
        )

    def run(self) -> int:
        """Prepare pre-match state and build final immutable forecasts.

        T-60:
            Pre-match monitoring becomes active.

        T-60 -> T-30:
            Starting XI may be checked on scheduled workflow runs.

        T-30:
            Missing lineup stops being a blocker. The system continues
            without a verified XI.

        T-15:
            The immutable final prediction is created.

        Telegram delivery remains a separate phase.
        """
        now = datetime.now(UTC)

        self.logger.info(
            "prediction_started utc=%s threshold=%.1f",
            now.isoformat(),
            self.settings.minimum_probability,
        )

        stats = dict(
            outside_window=0,
            analysis_active=0,
            lineup_checked=0,
            lineup_verified=0,
            lineup_fallback=0,
            waiting_final_window=0,
            already_locked=0,
            build_failed=0,
            eligible=0,
        )

        # --------------------------------------------------------------
        # Refresh historical results without allowing provider
        # corrections to terminate the prediction run.
        # --------------------------------------------------------------
        conflicts = self.store.read(
            "result_conflicts",
            [],
        )

        history = merge_results(
            self.store.read(
                "results",
                [],
            ),
            self.collector.results(
                self.settings.league_id
            ),
            conflicts,
        )

        self.store.write(
            "results",
            history,
        )

        self.store.write(
            "result_conflicts",
            conflicts,
        )

        forecasts = self.store.read(
            "forecasts",
            [],
        )

        published = self.store.read(
            "predictions",
            [],
        )

        locked = {
            str(row["fixture_id"])
            for row in forecasts + published
        }

        analysis_state = self.store.read(
            "pre_match_analysis",
            {},
        )

        if not isinstance(
            analysis_state,
            dict,
        ):
            analysis_state = {}

        count = 0

        fixtures = self.collector.fixtures(
            self.settings.league_id
        )

        self.logger.info(
            "prediction_data fixtures=%s "
            "historical_results=%s "
            "conflicts=%s",
            len(fixtures),
            len(history),
            len(conflicts),
        )

        if fixtures:
            future_fixtures = [
                fixture
                for fixture in fixtures
                if fixture.start > now
            ]

            if future_fixtures:
                nearest = min(
                    future_fixtures,
                    key=lambda fixture:
                        fixture.start,
                )

                self.logger.info(
                    "next_fixture fixture=%s - %s "
                    "kickoff_utc=%s "
                    "minutes_to_kickoff=%.1f",
                    nearest.home,
                    nearest.away,
                    nearest.start.isoformat(),
                    (
                        nearest.start
                        - now
                    ).total_seconds()
                    / 60,
                )

        # --------------------------------------------------------------
        # Process every fixture independently.
        #
        # We deliberately do not select only the nearest match. If several
        # Süper Lig fixtures share the same kickoff time, every eligible
        # fixture is handled during the same run.
        # --------------------------------------------------------------
        for fixture in fixtures:
            current = datetime.now(UTC)

            minutes = (
                fixture.start
                - current
            ).total_seconds() / 60

            key = str(
                fixture.id
            )

            if key in locked:
                stats[
                    "already_locked"
                ] += 1
                continue

            # Past/kicked-off fixtures and matches farther than T-60 need
            # no pre-match work.
            if (
                minutes <= 0
                or minutes
                > ANALYSIS_WINDOW_MINUTES
            ):
                stats[
                    "outside_window"
                ] += 1
                continue

            stats[
                "analysis_active"
            ] += 1

            state = analysis_state.get(
                key
            )

            if not isinstance(
                state,
                dict,
            ):
                state = {
                    "fixture_id":
                        fixture.id,
                    "fixture":
                        (
                            f"{fixture.home} - "
                            f"{fixture.away}"
                        ),
                    "home_team":
                        fixture.home,
                    "away_team":
                        fixture.away,
                    "kickoff":
                        fixture.start.isoformat(),
                    "analysis_started_at":
                        current.isoformat(),
                    "lineup_verified":
                        False,
                    "lineup_verified_at":
                        None,
                    "last_lineup_check_at":
                        None,
                    "lineup_fallback":
                        False,
                    "lineup_fallback_at":
                        None,
                    "updated_at":
                        current.isoformat(),
                }

            # ----------------------------------------------------------
            # T-60 -> T-30 lineup monitoring.
            #
            # If a complete XI has already been found, never request the
            # match detail again for this fixture.
            # ----------------------------------------------------------
            if (
                minutes
                > LINEUP_CHECK_UNTIL_MINUTES
                and not bool(
                    state.get(
                        "lineup_verified"
                    )
                )
            ):
                stats[
                    "lineup_checked"
                ] += 1

                state[
                    "last_lineup_check_at"
                ] = current.isoformat()

                try:
                    verified = (
                        self._lineup_verified(
                            self.collector.match(
                                fixture.id
                            )
                        )
                    )

                    if verified:
                        state[
                            "lineup_verified"
                        ] = True

                        state[
                            "lineup_verified_at"
                        ] = (
                            datetime.now(
                                UTC
                            ).isoformat()
                        )

                        stats[
                            "lineup_verified"
                        ] += 1

                        self.logger.info(
                            "lineup_verified "
                            "fixture_id=%s "
                            "minutes_to_kickoff=%.1f",
                            fixture.id,
                            minutes,
                        )

                    else:
                        self.logger.info(
                            "lineup_not_yet_available "
                            "fixture_id=%s "
                            "minutes_to_kickoff=%.1f",
                            fixture.id,
                            minutes,
                        )

                except Exception as exc:
                    self.logger.warning(
                        "lineup_check_failed "
                        "fixture_id=%s "
                        "minutes_to_kickoff=%.1f "
                        "error=%s",
                        fixture.id,
                        minutes,
                        type(exc).__name__,
                    )

            # ----------------------------------------------------------
            # At T-30 the lineup requirement is permanently released.
            #
            # This does not claim that a lineup exists. It records that
            # absence of a verified XI is no longer allowed to prevent the
            # final T-15 prediction.
            # ----------------------------------------------------------
            if (
                minutes
                <= LINEUP_CHECK_UNTIL_MINUTES
                and not bool(
                    state.get(
                        "lineup_verified"
                    )
                )
                and not bool(
                    state.get(
                        "lineup_fallback"
                    )
                )
            ):
                state[
                    "lineup_fallback"
                ] = True

                state[
                    "lineup_fallback_at"
                ] = current.isoformat()

                stats[
                    "lineup_fallback"
                ] += 1

                self.logger.info(
                    "lineup_fallback_enabled "
                    "fixture_id=%s "
                    "minutes_to_kickoff=%.1f",
                    fixture.id,
                    minutes,
                )

            state[
                "updated_at"
            ] = datetime.now(
                UTC
            ).isoformat()

            analysis_state[
                key
            ] = state

            # Persist the state immediately so another workflow run can
            # continue from the same immutable pre-match evidence.
            self.store.write(
                "pre_match_analysis",
                analysis_state,
            )

            # ----------------------------------------------------------
            # T-60 -> T-15 is monitoring only.
            #
            # No immutable prediction is created and no Telegram delivery
            # can be reserved before the final window.
            # ----------------------------------------------------------
            if (
                minutes
                > FINAL_PREDICTION_MINUTES
            ):
                stats[
                    "waiting_final_window"
                ] += 1
                continue

            # ----------------------------------------------------------
            # T-15 final prediction.
            #
            # A final detail lookup is allowed here only when the XI has
            # not already been verified. Missing XI can never block the
            # prediction after the T-30 fallback point.
            # ----------------------------------------------------------
            prediction = self._build(
                fixture,
                analysis_state.get(
                    key,
                    {},
                ),
            )

            if prediction is None:
                stats[
                    "build_failed"
                ] += 1

                self.logger.info(
                    "prediction_skipped "
                    "fixture_id=%s "
                    "reason="
                    "kickoff_reached_during_build",
                    fixture.id,
                )

                continue

            # Every successfully built final prediction is publishable.
            # Confidence and data quality remain in the prediction payload.
            payload = prediction.payload()
            payload["publishable"] = True
            forecasts.append(payload)

            # Persist the immutable forecast before publication/reservation.
            self.store.write(
                "forecasts",
                forecasts,
            )
            locked.add(key)

            published.append(prediction.payload())
            self.store.write(
                "predictions",
                published,
            )
            stats["eligible"] += 1
            count += 1

        # --------------------------------------------------------------
        # Remove stale pre-match state only after fixtures have kicked off.
        #
        # Historical forecast/performance data is stored elsewhere, so
        # pre_match_analysis only needs active future fixtures.
        # --------------------------------------------------------------
        active_fixture_ids = {
            str(fixture.id)
            for fixture in fixtures
            if fixture.start
            > datetime.now(UTC)
        }

        stale_analysis = [
            key
            for key
            in analysis_state
            if key
            not in active_fixture_ids
        ]

        for key in stale_analysis:
            analysis_state.pop(
                key,
                None,
            )

        self.store.write(
            "pre_match_analysis",
            analysis_state,
        )

        # --------------------------------------------------------------
        # Backward-compatible recovery:
        # eligible forecasts that were persisted before predictions.json
        # was updated are copied into predictions.json.
        # --------------------------------------------------------------
        ids = {
            str(
                prediction[
                    "fixture_id"
                ]
            )
            for prediction
            in published
        }

        for row in forecasts:
            key = str(
                row["fixture_id"]
            )

            if (
                row.get(
                    "publishable"
                )
                and key not in ids
            ):
                published.append(
                    {
                        name: value
                        for name, value
                        in row.items()
                        if name
                        != "publishable"
                    }
                )

                ids.add(
                    key
                )

        self.store.write(
            "predictions",
            published,
        )

        # Reserve before Telegram delivery.
        self._reserve_delivery(
            published
        )

        self.logger.info(
            "prediction_summary "
            "fixtures=%s "
            "new_eligible=%s %s",
            len(fixtures),
            count,
            " ".join(
                f"{key}={value}"
                for key, value
                in stats.items()
            ),
        )

        return count

    def _reserve_delivery(
        self,
        published: list,
    ) -> int:
        """Reserve eligible messages before workflow state is pushed."""
        from learning.adaptive import (
            timestamp,
        )

        delivery = self.store.read(
            "delivery",
            {},
        )

        reserved = 0
        now = datetime.now(UTC)

        for row in published:
            key = str(
                row["fixture_id"]
            )

            state = delivery.get(
                key
            )

            # Legacy string values mean the prediction was already
            # delivered. Existing attempting/delivered reservations
            # must never be duplicated.
            if (
                isinstance(
                    state,
                    str,
                )
                or (
                    isinstance(
                        state,
                        dict,
                    )
                    and state.get(
                        "status"
                    )
                    in {
                        "attempting",
                        "delivered",
                    }
                )
            ):
                continue

            if (
                not row.get(
                    "kickoff"
                )
                or timestamp(
                    row["kickoff"]
                )
                <= now
            ):
                continue

            delivery[key] = {
                "status":
                    "attempting",
                "reserved_at":
                    now.isoformat(),
            }

            reserved += 1

        self.store.write(
            "delivery",
            delivery,
        )

        self.logger.info(
            "delivery_reserved count=%s; "
            "Telegram must run only after "
            "this state is pushed",
            reserved,
        )

        return reserved

    def deliver(self) -> int:
        """Send only persisted reservations.

        Any failed delivery makes the command return non-zero.
        """
        from learning.adaptive import (
            timestamp,
        )

        client = TelegramClient(
            self.settings.prediction_token,
            self.settings.prediction_chat_id,
        )

        delivery = self.store.read(
            "delivery",
            {},
        )

        predictions = {
            str(
                prediction[
                    "fixture_id"
                ]
            ): prediction
            for prediction
            in self.store.read(
                "predictions",
                [],
            )
        }

        failures = 0
        sent = 0
        now = datetime.now(UTC)

        if not client.enabled:
            pending = [
                key
                for key, value
                in delivery.items()
                if (
                    isinstance(
                        value,
                        dict,
                    )
                    and value.get(
                        "status"
                    )
                    == "attempting"
                )
            ]

            if pending:
                self.logger.error(
                    "telegram_disabled "
                    "pending=%s "
                    "reason="
                    "missing_credentials",
                    len(pending),
                )

                return 1

            return 0

        for key, state in list(
            delivery.items()
        ):
            if (
                not isinstance(
                    state,
                    dict,
                )
                or state.get(
                    "status"
                )
                != "attempting"
            ):
                continue

            row = predictions.get(
                str(key)
            )

            if not row:
                failures += 1

                self.logger.error(
                    "prediction_delivery_failed "
                    "fixture_id=%s "
                    "reason="
                    "missing_persisted_prediction",
                    key,
                )

                continue

            if (
                not row.get(
                    "kickoff"
                )
                or timestamp(
                    row["kickoff"]
                )
                <= now
            ):
                delivery[key] = {
                    **state,
                    "status":
                        "expired",
                    "updated_at":
                        datetime.now(
                            UTC
                        ).isoformat(),
                }

                failures += 1
                continue

            try:
                prediction = Prediction(
                    **row
                )

            except TypeError:
                failures += 1

                self.logger.exception(
                    "prediction_delivery_failed "
                    "fixture_id=%s "
                    "reason="
                    "invalid_prediction_payload",
                    key,
                )

                continue

            if client.send_prediction(
                prediction
            ):
                delivery[key] = {
                    **state,
                    "status":
                        "delivered",
                    "delivered_at":
                        datetime.now(
                            UTC
                        ).isoformat(),
                }

                sent += 1

                self.logger.info(
                    "prediction_delivered "
                    "fixture_id=%s",
                    key,
                )

            else:
                delivery[key] = {
                    **state,
                    "status":
                        "failed",
                    "failed_at":
                        datetime.now(
                            UTC
                        ).isoformat(),
                }

                failures += 1

                self.logger.error(
                    "prediction_delivery_failed "
                    "fixture_id=%s",
                    key,
                )

        self.store.write(
            "delivery",
            delivery,
        )

        self.logger.info(
            "delivery_summary "
            "sent=%s failed=%s",
            sent,
            failures,
        )

        return (
            1
            if failures
            else 0
        )

    def _build(
        self,
        fixture,
        analysis_state: dict | None = None,
    ):
        """Build one immutable final pre-match prediction."""
        as_of = datetime.now(UTC)

        home, away = forms(
            self.store.read(
                "results",
                [],
            ),
            fixture.home,
            fixture.away,
            as_of,
        )

        state = (
            analysis_state
            if isinstance(
                analysis_state,
                dict,
            )
            else {}
        )

        verified = bool(
            state.get(
                "lineup_verified",
                False,
            )
        )

        # One final lineup lookup is allowed at T-15 if a complete XI was
        # not found earlier. Failure or absence never blocks prediction.
        if not verified:
            try:
                verified = (
                    self._lineup_verified(
                        self.collector.match(
                            fixture.id
                        )
                    )
                )

                if verified:
                    state[
                        "lineup_verified"
                    ] = True

                    state[
                        "lineup_verified_at"
                    ] = datetime.now(
                        UTC
                    ).isoformat()

                    state[
                        "updated_at"
                    ] = datetime.now(
                        UTC
                    ).isoformat()

                    analysis = self.store.read(
                        "pre_match_analysis",
                        {},
                    )

                    if not isinstance(
                        analysis,
                        dict,
                    ):
                        analysis = {}

                    analysis[
                        str(
                            fixture.id
                        )
                    ] = state

                    self.store.write(
                        "pre_match_analysis",
                        analysis,
                    )

            except Exception as exc:
                self.logger.warning(
                    "lineup_unavailable "
                    "fixture_id=%s "
                    "error=%s",
                    fixture.id,
                    type(exc).__name__,
                )

        # Never create a prediction after kickoff.
        if (
            datetime.now(UTC)
            >= fixture.start
        ):
            return None

        # Existing performance history drives adaptive-v2 expert weights.
        performance = self.store.read(
            "performance",
            [],
        )

        # Market-level adaptive learning state.
        learning_state = self.store.read(
            "learning_state",
            {},
        )

        engine = PredictionEngine(
            performance,
            learning_state,
        )

        prediction = engine.predict(
            fixture,
            home,
            away,
            lineup_verified=verified,
            as_of=as_of,
        )

        self.logger.info(
            "prediction_built "
            "fixture_id=%s "
            "lineup_verified=%s "
            "lineup_fallback=%s "
            "markets=%s",
            fixture.id,
            prediction.lineup_verified,
            bool(
                state.get(
                    "lineup_fallback",
                    False,
                )
            ),
            ",".join(
                prediction.markets.keys()
            )
            if prediction.markets
            else "none",
        )

        return prediction

    @staticmethod
    def _lineup_verified(
        detail,
    ):
        lineup = (
            detail.get(
                "content",
                {},
            )
            .get(
                "lineup",
                {},
            )
        )

        if not isinstance(
            lineup,
            dict,
        ):
            return False

        return all(
            isinstance(
                lineup.get(
                    side
                ),
                dict,
            )
            and len(
                lineup[
                    side
                ].get(
                    "starters"
                )
                or []
            )
            == 11
            for side in (
                "homeTeam",
                "awayTeam",
            )
        )
