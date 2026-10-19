"""Prediction scoring, reporting and adaptive-learning performance metrics."""

from __future__ import annotations

from collections import defaultdict
from math import log, sqrt

from learning.adaptive import (
    LABELS,
    MARKETS,
    build_learning_samples,
    normalize_learning_state,
    valid_probs,
)


MARKET_LABELS = {
    "1x2": "1X2",
    "ou25": "2.5 Alt/Üst",
    "btts": "KG Var/Yok",
}

COMBINED_SCORE_WEIGHTS = {
    "winner": 0.25,
    "exact_score": 0.25,
    "goal_markets": 0.20,
    "probability_quality": 0.20,
    "goal_distance": 0.10,
}



def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _safe_div(numerator: float, denominator: float) -> float | None:
    if denominator <= 0:
        return None
    return numerator / denominator


def _result_map(results: list[dict]) -> dict[str, dict]:
    return {
        str(row.get("fixture_id")): row
        for row in results
        if row.get("fixture_id") is not None
    }


def _goal_distance_score(prediction: dict, actual_home: int, actual_away: int) -> float | None:
    if "home_goals" not in prediction or "away_goals" not in prediction:
        return None

    try:
        predicted_home = int(prediction.get("home_goals"))
        predicted_away = int(prediction.get("away_goals"))
    except (TypeError, ValueError):
        return None

    total_error = abs(predicted_home - actual_home) + abs(predicted_away - actual_away)
    # Six total goal swings already represent a very poor forecast.
    return _clamp01(1.0 - min(1.0, total_error / 6.0))


def _probability_quality(probabilities: dict | None, label: str) -> float | None:
    if not valid_probs(probabilities):
        return None

    try:
        probability = max(float(probabilities[label]), 1e-15)
        log_quality = 1.0 - min(1.0, -log(probability) / log(3))
        brier_score = sum(
            (
                float(probabilities[key])
                - int(key == label)
            ) ** 2
            for key in LABELS
        )
        brier_quality = 1.0 - min(1.0, float(brier_score) / 2.0)
    except (KeyError, TypeError, ValueError):
        return None

    return (log_quality + brier_quality) / 2.0


def _record_combined_score(record: dict) -> float | None:
    components = []

    winner = record.get("winner_correct")
    if winner is not None:
        components.append(("winner", 1.0 if bool(winner) else 0.0))

    score = record.get("score_correct")
    if score is not None:
        components.append(("exact_score", 1.0 if bool(score) else 0.0))

    market_hits = []
    if "ou25_correct" in record:
        market_hits.append(1.0 if bool(record["ou25_correct"]) else 0.0)
    if "btts_correct" in record:
        market_hits.append(1.0 if bool(record["btts_correct"]) else 0.0)
    if market_hits:
        components.append(("goal_markets", sum(market_hits) / len(market_hits)))

    actual = record.get("actual_outcome")
    probability_quality = None
    if isinstance(actual, str):
        probability_quality = _probability_quality(record.get("probabilities"), actual)
    if probability_quality is not None:
        components.append(("probability_quality", probability_quality))

    actual_home = record.get("actual_home")
    actual_away = record.get("actual_away")
    if actual_home is not None and actual_away is not None:
        goal_distance = _goal_distance_score(record, int(actual_home), int(actual_away))
        if goal_distance is not None:
            components.append(("goal_distance", goal_distance))

    if not components:
        return None

    weighted_total = 0.0
    weight_total = 0.0

    for name, value in components:
        weight = COMBINED_SCORE_WEIGHTS.get(name, 0.0)
        weighted_total += weight * value
        weight_total += weight

    if weight_total <= 0:
        return None

    return round((weighted_total / weight_total) * 100.0, 2)


def _ranked_score(value: float | None) -> float | None:
    if value is None:
        return None
    return round(_clamp01(value / 100.0) * 100.0, 2)


def score_prediction(
    prediction: dict,
    home_goals: int | dict,
    away_goals: int | None = None,
) -> dict:
    """Score one settled forecast without changing its pre-match snapshot."""
    if isinstance(home_goals, dict):
        result_row = home_goals
        home_goals = int(
            result_row.get(
                "home_goals",
                result_row.get(
                    "actual_home",
                    0,
                ),
            )
        )
        away_goals = int(
            result_row.get(
                "away_goals",
                result_row.get(
                    "actual_away",
                    0,
                ),
            )
        )

    if away_goals is None:
        raise TypeError(
            "away_goals is required"
        )

    label = (
        "HOME"
        if home_goals > away_goals
        else "AWAY"
        if away_goals > home_goals
        else "DRAW"
    )

    teams = prediction[
        "fixture"
    ].split(
        " - ",
        1,
    )

    predicted_outcome = prediction.get(
        "outcome"
    )

    if predicted_outcome not in LABELS:
        predicted_team = (
            prediction.get(
                "predicted_winner"
            )
            or prediction.get(
                "winner"
            )
        )

        if len(teams) == 2:
            if predicted_team == teams[0]:
                predicted_outcome = "HOME"
            elif predicted_team == teams[1]:
                predicted_outcome = "AWAY"
            elif predicted_team == "Beraberlik":
                predicted_outcome = "DRAW"

    markets = prediction.get("markets", {}) if isinstance(prediction.get("markets"), dict) else {}
    ou_selection = str(markets.get("ou25", {}).get("selection", "")).upper()
    btts_selection = str(markets.get("btts", {}).get("selection", "")).upper()
    actual_ou = "OVER" if int(home_goals) + int(away_goals) > 2.5 else "UNDER"
    actual_btts = "YES" if int(home_goals) > 0 and int(away_goals) > 0 else "NO"

    winner_correct = predicted_outcome == label
    ou25_correct = ou_selection == actual_ou
    btts_correct = btts_selection == actual_btts
    score_correct = (
        int(prediction.get("home_goals", -1)) == int(home_goals)
        and int(prediction.get("away_goals", -1)) == int(away_goals)
    )

    result = {
        "actual_outcome": label,
        "actual_ou25": actual_ou,
        "actual_btts": actual_btts,
        "winner_correct": winner_correct,
        "ou25_correct": ou25_correct,
        "btts_correct": btts_correct,
        "score_correct": score_correct,
        "points": 10 * sum((winner_correct, ou25_correct, btts_correct, score_correct)),
        "max_points": 40,
    }

    probabilities = prediction.get(
        "probabilities"
    )

    if valid_probs(probabilities):
        probability = max(
            float(
                probabilities[label]
            ),
            1e-15,
        )

        result[
            "log_loss"
        ] = -log(
            probability
        )

        result[
            "brier_score"
        ] = sum(
            (
                float(
                    probabilities[key]
                )
                - int(key == label)
            ) ** 2
            for key in LABELS
        )

    return result


def calibration(
    records: list,
) -> float:
    """Observed winner accuracy over the latest 100 settled forecasts."""
    rows = [
        row
        for row in records
        if "winner_correct" in row
    ][-100:]

    if not rows:
        return 0.5

    return (
        sum(
            bool(
                row[
                    "winner_correct"
                ]
            )
            for row in rows
        )
        / len(rows)
    )


def _safe_mean(
    values: list[float],
) -> float | None:
    if not values:
        return None

    return (
        sum(values)
        / len(values)
    )


def _rate(
    correct: int,
    total: int,
) -> float | None:
    if total <= 0:
        return None

    return (
        correct
        / total
    )


def _percent(
    value: float | None,
) -> float | None:
    if value is None:
        return None

    return round(
        value * 100.0,
        2,
    )


def _is_eligible(
    record: dict,
) -> bool:
    """Return whether the forecast met publication conditions."""
    if "eligible" in record:
        return bool(
            record[
                "eligible"
            ]
        )

    if "publishable" in record:
        return bool(
            record[
                "publishable"
            ]
        )

    status = str(
        record.get(
            "status",
            "",
        )
    ).strip().lower()

    return status in {
        "eligible",
        "reserved",
        "attempting",
        "delivered",
        "sent",
    }


def _is_delivered(
    record: dict,
) -> bool:
    """Return whether Telegram delivery was actually confirmed."""
    if "delivered" in record:
        return bool(
            record[
                "delivered"
            ]
        )

    delivery = record.get(
        "delivery"
    )

    if isinstance(
        delivery,
        dict,
    ):
        status = str(
            delivery.get(
                "status",
                "",
            )
        ).strip().lower()

        if status in {
            "delivered",
            "sent",
            "success",
        }:
            return True

    status = str(
        record.get(
            "status",
            "",
        )
    ).strip().lower()

    return status in {
        "delivered",
        "sent",
    }


def _group(
    rows: list,
) -> dict:
    """Build backward-compatible aggregate forecast metrics."""
    count = len(rows)

    scored = [
        row
        for row in rows
        if (
            isinstance(
                row.get(
                    "log_loss"
                ),
                (int, float),
            )
            and isinstance(
                row.get(
                    "brier_score"
                ),
                (int, float),
            )
        )
    ]

    winner_rows = [
        row
        for row in rows
        if "winner_correct" in row
    ]

    score_rows = [
        row
        for row in rows
        if "score_correct" in row
    ]

    winner_accuracy = (
        sum(
            bool(
                row[
                    "winner_correct"
                ]
            )
            for row in winner_rows
        )
        / len(winner_rows)
        if winner_rows
        else None
    )

    combined_scores = [
        _record_combined_score(row)
        for row in rows
    ]
    combined_scores = [
        score
        for score in combined_scores
        if score is not None
    ]

    return {
        "matches": count,
        "count": count,
        "accuracy":
            winner_accuracy,
        "winner_accuracy":
            winner_accuracy,
        "exact_score_accuracy": (
            sum(
                bool(
                    row[
                        "score_correct"
                    ]
                )
                for row in score_rows
            )
            / len(score_rows)
            if score_rows
            else None
        ),
        "combined_score": (
            sum(combined_scores) / len(combined_scores)
            if combined_scores
            else None
        ),
        "log_loss": (
            sum(
                float(
                    row[
                        "log_loss"
                    ]
                )
                for row in scored
            )
            / len(scored)
            if scored
            else None
        ),
        "brier_score": (
            sum(
                float(
                    row[
                        "brier_score"
                    ]
                )
                for row in scored
            )
            / len(scored)
            if scored
            else None
        ),
    }


def _reliability_bins(
    records: list,
) -> list:
    bins = []

    for low, high in (
        (0, 40),
        (40, 50),
        (50, 60),
        (60, 70),
        (70, 80),
        (80, 90),
        (90, 101),
    ):
        rows = []

        for row in records:
            try:
                confidence = float(
                    row[
                        "confidence"
                    ]
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

            if (
                low
                <= confidence
                < high
                and "winner_correct"
                in row
            ):
                rows.append(
                    row
                )

        if not rows:
            continue

        bins.append(
            {
                "range": [
                    low,
                    min(
                        high,
                        100,
                    ),
                ],
                "matches":
                    len(rows),
                "predicted": (
                    sum(
                        float(
                            row[
                                "confidence"
                            ]
                        )
                        for row in rows
                    )
                    / len(rows)
                    / 100.0
                ),
                "observed": (
                    sum(
                        bool(
                            row[
                                "winner_correct"
                            ]
                        )
                        for row in rows
                    )
                    / len(rows)
                ),
            }
        )

    return bins


def summarize(
    records: list,
) -> dict:
    """Build the existing metrics report with explicit delivery separation."""
    eligible = [
        row
        for row in records
        if _is_eligible(
            row
        )
    ]

    delivered = [
        row
        for row in records
        if _is_delivered(
            row
        )
    ]

    total = len(records)

    return {
        "all":
            _group(
                records
            ),
        "eligible":
            _group(
                eligible
            ),
        "delivered":
            _group(
                delivered
            ),

        # Backward-compatible alias.
        # "published" means publication-eligible,
        # not necessarily Telegram-delivered.
        "published":
            _group(
                eligible
            ),

        "combined":
            combined_performance(
                records
            ),

        "history":
            history_summary(
                records
            ),

        "eligible_coverage": (
            len(eligible)
            / total
            if total
            else None
        ),
        "delivery_coverage": (
            len(delivered)
            / total
            if total
            else None
        ),

        # Backward compatibility for code/reports
        # that still read the old coverage key.
        "coverage": (
            len(eligible)
            / total
            if total
            else None
        ),
        "reliability":
            _reliability_bins(
                records
            ),
    }


def publication_stats(
    predictions: list[dict],
) -> dict:
    """Separate eligible forecasts from confirmed Telegram deliveries."""
    total = len(
        predictions
    )

    eligible = sum(
        1
        for prediction
        in predictions
        if _is_eligible(
            prediction
        )
    )

    delivered = sum(
        1
        for prediction
        in predictions
        if _is_delivered(
            prediction
        )
    )

    return {
        "total_predictions":
            total,
        "eligible":
            eligible,
        "delivered":
            delivered,
        "not_delivered":
            max(
                0,
                eligible
                - delivered,
            ),
        "eligible_rate":
            _percent(
                eligible
                / total
                if total
                else None
            ),
        "delivery_rate_of_eligible":
            _percent(
                delivered
                / eligible
                if eligible
                else None
            ),
    }


def combined_performance(
    records: list[dict],
) -> dict:
    """Combined success score with separate field-level signals."""
    rows = [
        row
        for row in records
        if isinstance(row, dict)
    ]

    combined_scores = [
        _record_combined_score(row)
        for row in rows
    ]
    combined_scores = [
        score
        for score in combined_scores
        if score is not None
    ]

    field_scores = {
        "1x2": _group(rows).get("winner_accuracy"),
        "exact_score": _group(rows).get("exact_score_accuracy"),
        "combined": (
            sum(combined_scores) / len(combined_scores)
            if combined_scores
            else None
        ),
    }

    market_rows = {
        "ou25": [
            row for row in rows if "ou25_correct" in row
        ],
        "btts": [
            row for row in rows if "btts_correct" in row
        ],
    }

    for market, market_rows_list in market_rows.items():
        if market_rows_list:
            field_scores[market] = _rate(
                sum(1 for row in market_rows_list if row.get(f"{market}_correct")),
                len(market_rows_list),
            )

    return {
        "count": len(rows),
        "combined_score": (
            sum(combined_scores) / len(combined_scores)
            if combined_scores
            else None
        ),
        "field_scores": field_scores,
        "weights": COMBINED_SCORE_WEIGHTS,
    }


def history_summary(
    records: list[dict],
    *,
    chunk_size: int = 20,
    limit: int = 6,
) -> list[dict]:
    """Show the model's own history in chronological chunks."""
    eligible_rows = [
        row
        for row in records
        if isinstance(row, dict)
    ]

    def _sort_key(row: dict):
        value = row.get("settled_at") or row.get("kickoff") or row.get("created_at")
        try:
            return value or ""
        except TypeError:
            return ""

    eligible_rows = sorted(
        eligible_rows,
        key=_sort_key,
    )

    if chunk_size <= 0:
        chunk_size = 20

    chunks = [
        eligible_rows[i : i + chunk_size]
        for i in range(0, len(eligible_rows), chunk_size)
    ]

    history = []

    for index, chunk in enumerate(chunks[-limit:], 1):
        group = _group(chunk)
        history.append(
            {
                "period": index,
                "matches": len(chunk),
                "combined_score": group.get("combined_score"),
                "winner_accuracy": group.get("winner_accuracy"),
                "exact_score_accuracy": group.get("exact_score_accuracy"),
            }
        )

    return history


def shared_match_comparison(
    predictions: list[dict],
    results: list[dict],
) -> dict:
    """Compare component models on the exact same matches."""
    result_map = _result_map(results)
    rows = []

    for prediction in predictions:
        fixture_id = str(prediction.get("fixture_id"))
        actual = result_map.get(fixture_id)

        if not actual:
            continue

        home = actual.get("home_goals")
        away = actual.get("away_goals")

        try:
            home_goals = int(home)
            away_goals = int(away)
        except (TypeError, ValueError):
            continue

        actual_label = (
            "HOME"
            if home_goals > away_goals
            else "AWAY"
            if away_goals > home_goals
            else "DRAW"
        )

        probabilities = prediction.get("component_probabilities", {})
        if not isinstance(probabilities, dict):
            continue

        for model_name, probs in probabilities.items():
            if not valid_probs(probs):
                continue

            predicted_label = max(
                probs,
                key=lambda key: float(probs[key]),
            )

            rows.append(
                {
                    "model": model_name,
                    "fixture_id": fixture_id,
                    "actual_outcome": actual_label,
                    "predicted_outcome": predicted_label,
                    "winner_correct": predicted_label == actual_label,
                    "log_loss": -log(max(float(probs[actual_label]), 1e-15)),
                    "brier_score": sum(
                        (
                            float(probs[key])
                            - int(key == actual_label)
                        ) ** 2
                        for key in LABELS
                    ),
                }
            )

    grouped = defaultdict(list)

    for row in rows:
        grouped[row["model"]].append(row)

    output = {}

    for model, model_rows in sorted(grouped.items()):
        output[model] = _group(model_rows)
        output[model]["matches"] = len(model_rows)

    return {
        "matches": len({row["fixture_id"] for row in rows}),
        "models": output,
    }


def market_performance(
    predictions: list[dict],
    results: list[dict],
    *,
    delivered_only: bool = False,
) -> dict[str, dict]:
    """Evaluate 1X2, O/U 2.5 and BTTS independently."""
    samples = build_learning_samples(
        predictions,
        results,
        delivered_only=delivered_only,
    )

    grouped = {
        market: []
        for market in MARKETS
    }

    for sample in samples:
        market = sample.get(
            "market"
        )

        if market in grouped:
            grouped[
                market
            ].append(
                sample
            )

    output = {}

    for market in MARKETS:
        rows = grouped[
            market
        ]

        total = len(
            rows
        )

        correct = sum(
            1
            for row in rows
            if row[
                "correct"
            ]
        )

        wrong = (
            total
            - correct
        )

        accuracy = _rate(
            correct,
            total,
        )

        mean_confidence = (
            sum(
                float(
                    row[
                        "confidence"
                    ]
                )
                for row in rows
            )
            / total
            if total
            else None
        )

        calibration_gap = (
            mean_confidence
            - accuracy * 100.0
            if (
                mean_confidence
                is not None
                and accuracy
                is not None
            )
            else None
        )

        last_20 = rows[
            -20:
        ]

        last_30 = rows[
            -30:
        ]

        last_20_correct = sum(
            1
            for row in last_20
            if row[
                "correct"
            ]
        )

        last_30_correct = sum(
            1
            for row in last_30
            if row[
                "correct"
            ]
        )

        last_20_error = (
            1.0
            - last_20_correct
            / len(
                last_20
            )
            if last_20
            else None
        )

        last_30_error = (
            1.0
            - last_30_correct
            / len(
                last_30
            )
            if last_30
            else None
        )

        output[
            market
        ] = {
            "label":
                MARKET_LABELS[
                    market
                ],
            "samples":
                total,
            "correct":
                correct,
            "wrong":
                wrong,
            "accuracy":
                _percent(
                    accuracy
                ),
            "error_rate":
                _percent(
                    1.0
                    - accuracy
                    if accuracy
                    is not None
                    else None
                ),
            "mean_confidence": (
                round(
                    mean_confidence,
                    2,
                )
                if mean_confidence
                is not None
                else None
            ),
            "calibration_gap": (
                round(
                    calibration_gap,
                    2,
                )
                if calibration_gap
                is not None
                else None
            ),
            "recent_20_samples":
                len(
                    last_20
                ),
            "recent_20_error_rate":
                _percent(
                    last_20_error
                ),
            "recent_30_samples":
                len(
                    last_30
                ),
            "recent_30_error_rate":
                _percent(
                    last_30_error
                ),
        }

    return output


def factor_performance(
    predictions: list[dict],
    results: list[dict],
    *,
    delivered_only: bool = False,
) -> dict[str, dict[str, dict]]:
    """Compare factor contribution in correct and incorrect predictions."""
    samples = build_learning_samples(
        predictions,
        results,
        delivered_only=delivered_only,
    )

    output = {
        market: {}
        for market in MARKETS
    }

    for market in MARKETS:
        market_rows = [
            row
            for row in samples
            if row.get(
                "market"
            )
            == market
        ]

        factor_names = set()

        for row in market_rows:
            factors = row.get(
                "factors",
                {},
            )

            if isinstance(
                factors,
                dict,
            ):
                factor_names.update(
                    factors.keys()
                )

        for factor in sorted(
            factor_names
        ):
            correct_values = []
            wrong_values = []

            for row in market_rows:
                try:
                    value = abs(
                        float(
                            row.get(
                                "factors",
                                {},
                            ).get(
                                factor,
                                0.0,
                            )
                        )
                    )

                except (
                    TypeError,
                    ValueError,
                ):
                    continue

                if row[
                    "correct"
                ]:
                    correct_values.append(
                        value
                    )
                else:
                    wrong_values.append(
                        value
                    )

            correct_mean = (
                _safe_mean(
                    correct_values
                )
                or 0.0
            )

            wrong_mean = (
                _safe_mean(
                    wrong_values
                )
                or 0.0
            )

            output[
                market
            ][
                factor
            ] = {
                "correct_samples":
                    len(
                        correct_values
                    ),
                "wrong_samples":
                    len(
                        wrong_values
                    ),
                "correct_mean_contribution":
                    round(
                        correct_mean,
                        6,
                    ),
                "wrong_mean_contribution":
                    round(
                        wrong_mean,
                        6,
                    ),
                "difference":
                    round(
                        correct_mean
                        - wrong_mean,
                        6,
                    ),
            }

    return output


def learning_performance(
    learning_state: dict | None,
) -> dict[str, dict]:
    """Create a human-readable view of the persistent learning state."""
    state = normalize_learning_state(
        learning_state
    )

    output = {}

    for market in MARKETS:
        data = state[
            "markets"
        ][
            market
        ]

        recent_20 = data.get(
            "recent_20",
            {},
        )

        recent_30 = data.get(
            "recent_30",
            {},
        )

        calibration_data = data.get(
            "calibration",
            {},
        )

        output[
            market
        ] = {
            "label":
                MARKET_LABELS[
                    market
                ],
            "status":
                data.get(
                    "status",
                    "collecting",
                ),
            "total_samples":
                int(
                    data.get(
                        "total_samples",
                        0,
                    )
                ),
            "season_accuracy":
                _percent(
                    data.get(
                        "season_accuracy"
                    )
                ),
            "recent_20_error_rate":
                _percent(
                    recent_20.get(
                        "error_rate"
                    )
                ),
            "recent_30_error_rate":
                _percent(
                    recent_30.get(
                        "error_rate"
                    )
                ),
            "calibration_multiplier":
                round(
                    float(
                        data.get(
                            "calibration_multiplier",
                            1.0,
                        )
                    ),
                    6,
                ),
            "mean_confidence":
                _percent(
                    calibration_data.get(
                        "mean_confidence"
                    )
                ),
            "calibration_accuracy":
                _percent(
                    calibration_data.get(
                        "accuracy"
                    )
                ),
            "calibration_gap":
                _percent(
                    calibration_data.get(
                        "gap"
                    )
                ),
            "weights": {
                key: round(
                    float(
                        value
                    ),
                    6,
                )
                for key, value
                in (
                    data.get(
                        "weights",
                        {},
                    )
                ).items()
            },
            "last_review_at":
                data.get(
                    "last_review_at"
                ),
            "last_adapted_at":
                data.get(
                    "last_adapted_at"
                ),
        }

    return output


def overall_performance(
    predictions: list[dict],
    results: list[dict],
    learning_state: dict | None = None,
) -> dict:
    """Full performance report for the adaptive layer."""
    eligible_predictions = [
        prediction
        for prediction in predictions
        if _is_eligible(
            prediction
        )
    ]

    delivered_predictions = [
        prediction
        for prediction in predictions
        if _is_delivered(
            prediction
        )
    ]

    report = {
        "publication":
            publication_stats(
                predictions
            ),
        "eligible_market_performance":
            market_performance(
                eligible_predictions,
                results,
            ),
        "delivered_market_performance":
            market_performance(
                delivered_predictions,
                results,
            ),
        "factor_performance":
            factor_performance(
                eligible_predictions,
                results,
            ),
        "same_match_comparison":
            shared_match_comparison(
                eligible_predictions,
                results,
            ),
        "history":
            history_summary(
                eligible_predictions,
            ),
        "combined":
            combined_performance(
                eligible_predictions,
            ),
    }

    if learning_state is not None:
        report[
            "learning"
        ] = learning_performance(
            learning_state
        )

    return report


def summarize_performance(
    predictions: list[dict],
    results: list[dict],
    learning_state: dict | None = None,
) -> dict:
    """Alias for callers using the newer performance API."""
    return overall_performance(
        predictions,
        results,
        learning_state,
    )


def performance_summary(
    predictions: list[dict],
    results: list[dict],
    learning_state: dict | None = None,
) -> dict:
    """Backward-compatible alias for full adaptive reporting."""
    return overall_performance(
        predictions,
        results,
        learning_state,
    )
