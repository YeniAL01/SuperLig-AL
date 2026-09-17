"""Performance evaluation for Süper Lig AL predictions.

This module keeps prediction quality, publication eligibility and actual
Telegram delivery as separate concepts. It also exposes market-level
statistics used by the adaptive learning layer.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from learning.adaptive import (
    MARKETS,
    build_learning_samples,
    normalize_learning_state,
)


MARKET_LABELS = {
    "1x2": "1X2",
    "ou25": "2.5 Alt/Üst",
    "btts": "KG Var/Yok",
}


def _rate(correct: int, total: int) -> float | None:
    if total <= 0:
        return None
    return correct / total


def _percent(value: float | None) -> float | None:
    if value is None:
        return None
    return round(value * 100.0, 2)


def _is_eligible(prediction: dict) -> bool:
    """Return whether a prediction satisfied publication conditions."""
    if "eligible" in prediction:
        return bool(prediction["eligible"])

    status = str(
        prediction.get("status", "")
    ).strip().lower()

    return status in {
        "eligible",
        "reserved",
        "attempting",
        "delivered",
        "sent",
    }


def _is_delivered(prediction: dict) -> bool:
    """Return whether Telegram delivery was actually confirmed."""
    if "delivered" in prediction:
        return bool(prediction["delivered"])

    delivery = prediction.get("delivery")

    if isinstance(delivery, dict):
        status = str(
            delivery.get("status", "")
        ).strip().lower()

        if status in {"delivered", "sent", "success"}:
            return True

    status = str(
        prediction.get("status", "")
    ).strip().lower()

    return status in {"delivered", "sent"}


def publication_stats(predictions: list[dict]) -> dict:
    """Separate eligible predictions from confirmed Telegram deliveries."""
    total = len(predictions)

    eligible = sum(
        1
        for prediction in predictions
        if _is_eligible(prediction)
    )

    delivered = sum(
        1
        for prediction in predictions
        if _is_delivered(prediction)
    )

    delivery_failed = sum(
        1
        for prediction in predictions
        if _is_eligible(prediction)
        and not _is_delivered(prediction)
        and str(
            (
                prediction.get("delivery") or {}
            ).get("status", "")
            if isinstance(
                prediction.get("delivery"),
                dict,
            )
            else ""
        ).lower()
        in {"failed", "error"}
    )

    return {
        "total_predictions": total,
        "eligible": eligible,
        "delivered": delivered,
        "delivery_failed": delivery_failed,
        "eligible_rate": _percent(
            eligible / total
            if total
            else None
        ),
        "delivery_rate_of_eligible": _percent(
            delivered / eligible
            if eligible
            else None
        ),
    }


def market_performance(
    predictions: list[dict],
    results: list[dict],
    *,
    delivered_only: bool = False,
) -> dict[str, dict]:
    """Calculate independent accuracy and calibration for every market."""
    samples = build_learning_samples(
        predictions,
        results,
        delivered_only=delivered_only,
    )

    grouped: dict[str, list[dict]] = {
        market: []
        for market in MARKETS
    }

    for sample in samples:
        market = sample["market"]

        if market in grouped:
            grouped[market].append(sample)

    output: dict[str, dict] = {}

    for market in MARKETS:
        rows = grouped[market]

        total = len(rows)
        correct = sum(
            1
            for row in rows
            if row["correct"]
        )
        wrong = total - correct

        accuracy = _rate(correct, total)

        mean_confidence = (
            sum(
                float(row["confidence"])
                for row in rows
            )
            / total
            if total
            else None
        )

        calibration_gap = (
            mean_confidence
            - (accuracy * 100.0)
            if (
                mean_confidence is not None
                and accuracy is not None
            )
            else None
        )

        last_20 = rows[-20:]
        last_30 = rows[-30:]

        last_20_correct = sum(
            1
            for row in last_20
            if row["correct"]
        )
        last_30_correct = sum(
            1
            for row in last_30
            if row["correct"]
        )

        last_20_error = (
            1.0 - (
                last_20_correct / len(last_20)
            )
            if last_20
            else None
        )

        last_30_error = (
            1.0 - (
                last_30_correct / len(last_30)
            )
            if last_30
            else None
        )

        output[market] = {
            "label": MARKET_LABELS[market],
            "samples": total,
            "correct": correct,
            "wrong": wrong,
            "accuracy": _percent(accuracy),
            "error_rate": _percent(
                1.0 - accuracy
                if accuracy is not None
                else None
            ),
            "mean_confidence": (
                round(mean_confidence, 2)
                if mean_confidence is not None
                else None
            ),
            "calibration_gap": (
                round(calibration_gap, 2)
                if calibration_gap is not None
                else None
            ),
            "recent_20_samples": len(last_20),
            "recent_20_error_rate": _percent(
                last_20_error
            ),
            "recent_30_samples": len(last_30),
            "recent_30_error_rate": _percent(
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
    """Show which factor strengths occur in correct vs wrong predictions."""
    samples = build_learning_samples(
        predictions,
        results,
        delivered_only=delivered_only,
    )

    grouped: dict[
        str,
        dict[str, dict[str, list[float]]],
    ] = defaultdict(
        lambda: defaultdict(
            lambda: {
                "correct": [],
                "wrong": [],
            }
        )
    )

    for sample in samples:
        market = sample["market"]

        for factor, raw_value in sample[
            "factors"
        ].items():
            try:
                value = abs(float(raw_value))
            except (TypeError, ValueError):
                continue

            bucket = (
                "correct"
                if sample["correct"]
                else "wrong"
            )

            grouped[market][factor][
                bucket
            ].append(value)

    output: dict[
        str,
        dict[str, dict],
    ] = {}

    for market in MARKETS:
        output[market] = {}

        for factor, buckets in grouped[
            market
        ].items():
            correct_values = buckets[
                "correct"
            ]
            wrong_values = buckets[
                "wrong"
            ]

            correct_mean = (
                sum(correct_values)
                / len(correct_values)
                if correct_values
                else 0.0
            )

            wrong_mean = (
                sum(wrong_values)
                / len(wrong_values)
                if wrong_values
                else 0.0
            )

            output[market][factor] = {
                "correct_samples": len(
                    correct_values
                ),
                "wrong_samples": len(
                    wrong_values
                ),
                "correct_mean_contribution": round(
                    correct_mean,
                    6,
                ),
                "wrong_mean_contribution": round(
                    wrong_mean,
                    6,
                ),
                "difference": round(
                    correct_mean
                    - wrong_mean,
                    6,
                ),
            }

    return output


def learning_performance(
    learning_state: dict | None,
) -> dict[str, dict]:
    """Return a report-friendly view of the persistent learning state."""
    state = normalize_learning_state(
        learning_state
    )

    output: dict[str, dict] = {}

    for market in MARKETS:
        data = state["markets"][market]

        recent_20 = data.get(
            "recent_20",
            {},
        )

        recent_30 = data.get(
            "recent_30",
            {},
        )

        calibration = data.get(
            "calibration",
            {},
        )

        output[market] = {
            "label": MARKET_LABELS[market],
            "status": data.get(
                "status",
                "collecting",
            ),
            "total_samples": int(
                data.get(
                    "total_samples",
                    0,
                )
            ),
            "season_accuracy": _percent(
                data.get(
                    "season_accuracy"
                )
            ),
            "recent_20_error_rate": _percent(
                recent_20.get(
                    "error_rate"
                )
            ),
            "recent_30_error_rate": _percent(
                recent_30.get(
                    "error_rate"
                )
            ),
            "calibration_multiplier": round(
                float(
                    data.get(
                        "calibration_multiplier",
                        1.0,
                    )
                ),
                6,
            ),
            "mean_confidence": _percent(
                calibration.get(
                    "mean_confidence"
                )
            ),
            "calibration_accuracy": _percent(
                calibration.get(
                    "accuracy"
                )
            ),
            "calibration_gap": _percent(
                calibration.get(
                    "gap"
                )
            ),
            "weights": {
                key: round(
                    float(value),
                    6,
                )
                for key, value in (
                    data.get(
                        "weights",
                        {},
                    )
                ).items()
            },
            "last_review_at": data.get(
                "last_review_at"
            ),
            "last_adapted_at": data.get(
                "last_adapted_at"
            ),
        }

    return output


def overall_performance(
    predictions: list[dict],
    results: list[dict],
    learning_state: dict | None = None,
) -> dict:
    """Build the complete performance view used by reports.

    Two market views are intentionally returned:

    ``eligible_market_performance``
        Settled predictions that satisfied publication conditions.

    ``delivered_market_performance``
        Settled predictions that were confirmed as delivered to Telegram.

    This prevents a Telegram delivery failure from being counted as if the
    user actually received the prediction.
    """
    eligible_predictions = [
        prediction
        for prediction in predictions
        if _is_eligible(prediction)
    ]

    delivered_predictions = [
        prediction
        for prediction in predictions
        if _is_delivered(prediction)
    ]

    report = {
        "publication": publication_stats(
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
    }

    if learning_state is not None:
        report["learning"] = (
            learning_performance(
                learning_state
            )
        )

    return report


def summarize_performance(
    predictions: list[dict],
    results: list[dict],
    learning_state: dict | None = None,
) -> dict:
    """Backward-compatible public entry point."""
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
    """Alias retained for callers using the older function name."""
    return overall_performance(
        predictions,
        results,
        learning_state,
    )
