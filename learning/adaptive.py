"""Controlled adaptive learning for Süper Lig prediction models.

This module preserves the existing adaptive-v2 expert weighting mechanism
used by PredictionEngine while also providing a bounded market-level
learning state.

Important:
- Python source code is never rewritten by the learning process.
- Existing model_weights() behaviour remains backward compatible.
- 1X2, O/U 2.5 and BTTS can learn independently.
- Fewer than 20 settled samples means observation only.
- Last 20 error >= 35% triggers review status.
- At least 30 samples and last 30 error >= 40% allows adaptation.
- Last 30 error >= 50% marks the market critical.
- One adaptation cycle changes a factor by at most +/-5%.
- Factor weights remain within 75%-125% of baseline.
- Confidence calibration is bounded independently.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime, timedelta
from math import exp, isfinite, log
from typing import Any


LABELS = ("HOME", "DRAW", "AWAY")
MARKETS = ("1x2", "ou25", "btts")

MIN_REVIEW_SAMPLES = 20
MIN_ADAPT_SAMPLES = 30
MIN_OBSERVATION_PERIOD = timedelta(days=28)

REVIEW_ERROR_RATE = 0.35
ADAPT_ERROR_RATE = 0.40
CRITICAL_ERROR_RATE = 0.50

RECENT_REVIEW_WINDOW = 20
RECENT_ADAPT_WINDOW = 30

MAX_FACTOR_CHANGE_PER_CYCLE = 0.05
MIN_FACTOR_MULTIPLIER = 0.75
MAX_FACTOR_MULTIPLIER = 1.25

MAX_CALIBRATION_CHANGE_PER_CYCLE = 0.05
MIN_CALIBRATION_MULTIPLIER = 0.75
MAX_CALIBRATION_MULTIPLIER = 1.10

DEFAULT_FACTORS = {
    "form": 1.0,
    "home_away": 1.0,
    "elo": 1.0,
    "goals": 1.0,
    "lineup": 1.0,
    "availability": 1.0,
    "odds_support": 1.0,
    "model_signal": 1.0,
}


# ---------------------------------------------------------------------------
# Existing adaptive-v2 expert weighting
# ---------------------------------------------------------------------------

def timestamp(value: Any) -> datetime:
    """Return a timezone-aware datetime.

    Backward compatible with the original adaptive-v2 implementation while
    also accepting datetime objects used by the newer learning helpers.
    """
    if isinstance(value, datetime):
        dt = value
    else:
        text = str(value).strip()

        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

    if dt.tzinfo is None:
        raise ValueError("Timezone is required")

    return dt


def valid_probs(probs: object) -> bool:
    """Validate a HOME/DRAW/AWAY probability distribution."""
    return (
        isinstance(probs, dict)
        and set(probs) == set(LABELS)
        and all(
            isinstance(value, (float, int))
            and not isinstance(value, bool)
            and isfinite(value)
            and 0 < value < 1
            for value in probs.values()
        )
        and abs(sum(probs.values()) - 1) < 1e-6
    )


def eligible(records: list, cutoff: datetime) -> list:
    """Return valid settled adaptive-v2 records available by cutoff."""
    selected = []
    seen = set()

    for row in records:
        try:
            key = str(row["fixture_id"])

            if (
                key in seen
                or row.get("model_version") != "adaptive-v2"
                or not (
                    timestamp(row["created_at"])
                    < timestamp(row["kickoff"])
                    < timestamp(row["settled_at"])
                    <= cutoff
                )
            ):
                continue

            if row.get("actual_outcome") not in LABELS:
                continue

            selected.append(row)
            seen.add(key)

        except (KeyError, ValueError, TypeError):
            continue

    return sorted(
        selected,
        key=lambda row: timestamp(row["settled_at"]),
    )[-300:]


def model_weights(
    records: list,
    names: list[str],
    cutoff: datetime,
) -> dict:
    """Calculate regularized expert weights.

    This is the existing adaptive-v2 mechanism used directly by
    prediction.engine.PredictionEngine and main.py.

    It intentionally remains independent from the newer market-level learning
    state so existing forecasts continue working without a migration.
    """
    if not names:
        return {}

    rows = eligible(records, cutoff)

    # V1 baseline is observed for four full weeks before historical
    # performance is allowed to alter expert weights.
    if not rows or (rows[-1]["settled_at"] and (
        timestamp(rows[-1]["settled_at"]) - timestamp(rows[0]["settled_at"])
    ) < MIN_OBSERVATION_PERIOD):
        return {name: 1.0 / len(names) for name in names}

    scores = {}

    for name in names:
        loss = 20 * log(3)
        mass = 20.0

        for age, row in enumerate(reversed(rows)):
            probabilities = row.get(
                "component_probabilities",
                {},
            ).get(name)

            if valid_probs(probabilities):
                weight = 0.99 ** age

                loss += (
                    -log(
                        probabilities[
                            row["actual_outcome"]
                        ]
                    )
                    * weight
                )

                mass += weight

        scores[name] = exp(
            -3 * loss / mass
        )

    total = sum(scores.values())

    if total <= 0 or not isfinite(total):
        return {
            name: 1.0 / len(names)
            for name in names
        }

    return {
        name: (
            0.1 / len(names)
            + 0.9 * value / total
        )
        for name, value in scores.items()
    }


# ---------------------------------------------------------------------------
# Persistent market-level learning state
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _default_market_state() -> dict:
    return {
        "baseline_weights": deepcopy(
            DEFAULT_FACTORS
        ),
        "weights": deepcopy(
            DEFAULT_FACTORS
        ),
        "calibration_multiplier": 1.0,
        "total_samples": 0,
        "total_correct": 0,
        "total_wrong": 0,
        "season_accuracy": None,
        "recent_20_error_rate": None,
        "recent_30_error_rate": None,
        "recent_20": {
            "samples": 0,
            "correct": 0,
            "wrong": 0,
            "accuracy": None,
            "error_rate": None,
        },
        "recent_30": {
            "samples": 0,
            "correct": 0,
            "wrong": 0,
            "accuracy": None,
            "error_rate": None,
        },
        "calibration": {
            "samples": 0,
            "mean_confidence": None,
            "accuracy": None,
            "gap": None,
        },
        "status": "collecting",
        "last_review_at": None,
        "last_adapted_at": None,
        # Idempotency keys prevent daily learn jobs from reusing unchanged
        # settled evidence as though it were newly observed.
        "last_review_sample_key": None,
        "last_adapted_sample_key": None,
    }


def default_learning_state() -> dict:
    """Return a fresh persistent learning-state structure."""
    return {
        "version": 1,
        "updated_at": None,
        "markets": {
            market: _default_market_state()
            for market in MARKETS
        },
        "audit": [],
    }


def normalize_learning_state(
    state: dict | None,
) -> dict:
    """Normalize old/missing state without losing valid learned values."""
    normalized = default_learning_state()

    if not isinstance(state, dict):
        return normalized

    try:
        normalized["version"] = int(
            state.get("version", 1)
        )
    except (TypeError, ValueError):
        normalized["version"] = 1

    normalized["updated_at"] = state.get(
        "updated_at"
    )

    model_weights_state = state.get("model_weights")
    if isinstance(model_weights_state, dict):
        normalized["model_weights"] = deepcopy(model_weights_state)

    old_markets = state.get("markets", {})

    if isinstance(old_markets, dict):
        for market in MARKETS:
            old = old_markets.get(market)

            if not isinstance(old, dict):
                continue

            target = normalized[
                "markets"
            ][market]

            for key in (
                "calibration_multiplier",
                "total_samples",
                "total_correct",
                "total_wrong",
                "season_accuracy",
                "recent_20_error_rate",
                "recent_30_error_rate",
                "status",
                "last_review_at",
                "last_adapted_at",
                "last_review_sample_key",
                "last_adapted_sample_key",
            ):
                if key in old:
                    target[key] = old[key]

            baseline = old.get(
                "baseline_weights"
            )

            if isinstance(baseline, dict):
                for factor in DEFAULT_FACTORS:
                    try:
                        if factor in baseline:
                            target[
                                "baseline_weights"
                            ][factor] = float(
                                baseline[factor]
                            )
                    except (TypeError, ValueError):
                        pass

            weights = old.get("weights")

            if isinstance(weights, dict):
                for factor in DEFAULT_FACTORS:
                    try:
                        if factor in weights:
                            target[
                                "weights"
                            ][factor] = float(
                                weights[factor]
                            )
                    except (TypeError, ValueError):
                        pass

            for section in (
                "recent_20",
                "recent_30",
                "calibration",
            ):
                value = old.get(section)

                if isinstance(value, dict):
                    target[section].update(
                        value
                    )

    audit = state.get("audit", [])

    if isinstance(audit, list):
        normalized["audit"] = list(audit)

    return normalized


def factor_snapshot(
    *,
    form: float = 0.0,
    home_away: float = 0.0,
    elo: float = 0.0,
    goals: float = 0.0,
    lineup: float = 0.0,
    availability: float = 0.0,
    odds_support: float = 0.0,
    model_signal: float = 0.0,
) -> dict[str, float]:
    """Build a serializable factor snapshot for one prediction."""
    return {
        "form": float(form),
        "home_away": float(home_away),
        "elo": float(elo),
        "goals": float(goals),
        "lineup": float(lineup),
        "availability": float(
            availability
        ),
        "odds_support": float(
            odds_support
        ),
        "model_signal": float(
            model_signal
        ),
    }


def market_learning(
    state: dict | None,
    market: str,
) -> dict:
    """Return normalized learning state for one market."""
    if market not in MARKETS:
        raise ValueError(
            f"Unsupported market: {market}"
        )

    normalized = normalize_learning_state(
        state
    )

    return deepcopy(
        normalized["markets"][market]
    )


def weighted_factor_score(
    factors: dict[str, Any] | None,
    market_state: dict | None,
) -> float:
    """Apply learned factor weights to a factor snapshot."""
    if not isinstance(factors, dict):
        return 0.0

    state = (
        market_state
        if isinstance(market_state, dict)
        else {}
    )

    weights = state.get(
        "weights",
        DEFAULT_FACTORS,
    )

    total = 0.0
    normalizer = 0.0

    for factor, baseline in (
        DEFAULT_FACTORS.items()
    ):
        try:
            value = float(
                factors.get(factor, 0.0)
            )

            weight = float(
                weights.get(
                    factor,
                    baseline,
                )
            )

        except (TypeError, ValueError):
            continue

        total += value * weight
        normalizer += abs(weight)

    if normalizer <= 0:
        return 0.0

    return total / normalizer


def calibrated_confidence(
    confidence: float,
    market_state: dict | None,
) -> float:
    """Apply bounded confidence calibration."""
    try:
        raw = float(confidence)
    except (TypeError, ValueError):
        return 0.0

    multiplier = 1.0

    if isinstance(market_state, dict):
        try:
            multiplier = float(
                market_state.get(
                    "calibration_multiplier",
                    1.0,
                )
            )
        except (TypeError, ValueError):
            multiplier = 1.0

    return max(
        0.0,
        min(
            100.0,
            raw * multiplier,
        ),
    )


# ---------------------------------------------------------------------------
# Prediction/result normalization for learning
# ---------------------------------------------------------------------------

def _prediction_market(
    prediction: dict,
    market: str,
) -> dict | None:
    markets = prediction.get("markets")

    if isinstance(markets, dict):
        payload = markets.get(market)

        if isinstance(payload, dict):
            return payload

    aliases = {
        "1x2": (
            "1x2",
            "match_result",
        ),
        "ou25": (
            "ou25",
            "over_under_25",
            "over_under",
        ),
        "btts": (
            "btts",
            "both_teams_to_score",
        ),
    }

    for key in aliases[market]:
        payload = prediction.get(key)

        if isinstance(payload, dict):
            return payload

    return None


def _actual_outcome(
    result: dict,
    market: str,
) -> str:
    if "home_goals" in result:
        home = int(result["home_goals"])
    else:
        home = int(result["actual_home"])

    if "away_goals" in result:
        away = int(result["away_goals"])
    else:
        away = int(result["actual_away"])

    if market == "1x2":
        if home > away:
            return "home"

        if home < away:
            return "away"

        return "draw"

    if market == "ou25":
        return (
            "over"
            if home + away > 2.5
            else "under"
        )

    if market == "btts":
        return (
            "yes"
            if home > 0 and away > 0
            else "no"
        )

    raise ValueError(
        f"Unsupported market: {market}"
    )


def _normalize_selection(
    value: Any,
    market: str,
) -> str:
    text = str(value).strip().lower()

    aliases = {
        "1x2": {
            "1": "home",
            "home": "home",
            "ev": "home",
            "ev sahibi": "home",
            "x": "draw",
            "draw": "draw",
            "beraberlik": "draw",
            "2": "away",
            "away": "away",
            "deplasman": "away",
        },
        "ou25": {
            "over": "over",
            "üst": "over",
            "ust": "over",
            "over 2.5": "over",
            "2.5 üst": "over",
            "2.5 ust": "over",
            "under": "under",
            "alt": "under",
            "under 2.5": "under",
            "2.5 alt": "under",
        },
        "btts": {
            "yes": "yes",
            "var": "yes",
            "kg var": "yes",
            "no": "no",
            "yok": "no",
            "kg yok": "no",
        },
    }

    return aliases.get(
        market,
        {},
    ).get(
        text,
        text,
    )


def _extract_confidence(
    payload: dict,
) -> float:
    value = payload.get(
        "confidence",
        payload.get(
            "probability",
            0.0,
        ),
    )

    try:
        confidence = float(value)
    except (TypeError, ValueError):
        return 0.0

    if 0.0 <= confidence <= 1.0:
        confidence *= 100.0

    return max(
        0.0,
        min(
            100.0,
            confidence,
        ),
    )


def build_learning_samples(
    predictions: list,
    results: list,
    *,
    delivered_only: bool = False,
) -> list[dict]:
    """Build independent settled samples for 1X2/O-U2.5/BTTS.

    The function is intentionally tolerant of old records. Predictions that
    do not yet contain a specific market snapshot are skipped for that market
    instead of breaking the learning cycle.
    """
    result_index = {}

    for row in results:
        fixture_id = row.get("fixture_id")

        if fixture_id is not None:
            result_index[str(fixture_id)] = row

    samples = []

    for prediction in predictions:
        fixture_id = str(
            prediction.get(
                "fixture_id",
                "",
            )
        )

        result = result_index.get(
            fixture_id
        )

        if result is None:
            continue

        if (
            delivered_only
            and not bool(
                prediction.get(
                    "delivered"
                )
            )
        ):
            continue

        settled_at = (
            result.get("available_at")
            or result.get("settled_at")
            or prediction.get("settled_at")
            or result.get("kickoff")
            or prediction.get("kickoff")
        )

        if not settled_at:
            continue

        for market in MARKETS:
            payload = _prediction_market(
                prediction,
                market,
            )

            if payload is None:
                continue

            selection = (
                payload.get("selection")
                or payload.get("pick")
                or payload.get("prediction")
                or payload.get("outcome")
            )

            if selection is None:
                continue

            try:
                actual = _actual_outcome(
                    result,
                    market,
                )
            except (
                KeyError,
                TypeError,
                ValueError,
            ):
                continue

            predicted = _normalize_selection(
                selection,
                market,
            )

            factors = payload.get(
                "factors"
            )

            if not isinstance(
                factors,
                dict,
            ):
                snapshot = prediction.get(
                    "factor_snapshot",
                    {}
                )

                if isinstance(
                    snapshot,
                    dict,
                ):
                    factors = snapshot.get(
                        market,
                        {},
                    )
                else:
                    factors = {}

            normalized_factors = {}

            for factor in DEFAULT_FACTORS:
                try:
                    normalized_factors[
                        factor
                    ] = float(
                        factors.get(
                            factor,
                            0.0,
                        )
                    )
                except (
                    TypeError,
                    ValueError,
                ):
                    normalized_factors[
                        factor
                    ] = 0.0

            try:
                settled_iso = timestamp(
                    settled_at
                ).isoformat()
            except (
                TypeError,
                ValueError,
            ):
                continue

            samples.append(
                {
                    "fixture_id": fixture_id,
                    "market": market,
                    "predicted": predicted,
                    "actual": actual,
                    "correct": (
                        predicted == actual
                    ),
                    "confidence":
                        _extract_confidence(
                            payload
                        ),
                    "factors":
                        normalized_factors,
                    "settled_at":
                        settled_iso,
                }
            )

    return sorted(
        samples,
        key=lambda row: (
            timestamp(
                row["settled_at"]
            ),
            row["fixture_id"],
            row["market"],
        ),
    )


# ---------------------------------------------------------------------------
# Controlled adaptation
# ---------------------------------------------------------------------------

def _window_stats(
    samples: list[dict],
    size: int,
) -> dict:
    rows = samples[-size:]

    count = len(rows)

    correct = sum(
        1
        for row in rows
        if row["correct"]
    )

    wrong = count - correct

    accuracy = (
        correct / count
        if count
        else None
    )

    error_rate = (
        wrong / count
        if count
        else None
    )

    return {
        "samples": count,
        "correct": correct,
        "wrong": wrong,
        "accuracy": accuracy,
        "error_rate": error_rate,
    }


def _calibration_stats(
    samples: list[dict],
) -> dict:
    if not samples:
        return {
            "samples": 0,
            "mean_confidence": None,
            "accuracy": None,
            "gap": None,
        }

    count = len(samples)

    mean_confidence = (
        sum(
            row["confidence"]
            for row in samples
        )
        / count
        / 100.0
    )

    accuracy = (
        sum(
            1
            for row in samples
            if row["correct"]
        )
        / count
    )

    return {
        "samples": count,
        "mean_confidence":
            mean_confidence,
        "accuracy": accuracy,
        "gap": (
            mean_confidence
            - accuracy
        ),
    }


def _factor_quality(
    samples: list[dict],
    factor: str,
) -> tuple[float, float]:
    correct_values = []
    wrong_values = []

    for row in samples:
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

        if row["correct"]:
            correct_values.append(value)
        else:
            wrong_values.append(value)

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

    return (
        correct_mean,
        wrong_mean,
    )


def _bounded_weight(
    baseline: float,
    current: float,
    requested_change: float,
) -> float:
    cycle_change = max(
        -MAX_FACTOR_CHANGE_PER_CYCLE,
        min(
            MAX_FACTOR_CHANGE_PER_CYCLE,
            requested_change,
        ),
    )

    candidate = current * (
        1.0 + cycle_change
    )

    lower = (
        baseline
        * MIN_FACTOR_MULTIPLIER
    )

    upper = (
        baseline
        * MAX_FACTOR_MULTIPLIER
    )

    return max(
        lower,
        min(
            upper,
            candidate,
        ),
    )


def _adapt_factors(
    market_state: dict,
    recent: list[dict],
) -> list[dict]:
    changes = []

    for factor in DEFAULT_FACTORS:
        (
            correct_mean,
            wrong_mean,
        ) = _factor_quality(
            recent,
            factor,
        )

        if (
            correct_mean == 0.0
            and wrong_mean == 0.0
        ):
            continue

        baseline = float(
            market_state[
                "baseline_weights"
            ].get(
                factor,
                1.0,
            )
        )

        current = float(
            market_state[
                "weights"
            ].get(
                factor,
                baseline,
            )
        )

        denominator = max(
            correct_mean + wrong_mean,
            1e-9,
        )

        evidence = (
            correct_mean
            - wrong_mean
        ) / denominator

        requested = max(
            -MAX_FACTOR_CHANGE_PER_CYCLE,
            min(
                MAX_FACTOR_CHANGE_PER_CYCLE,
                evidence
                * MAX_FACTOR_CHANGE_PER_CYCLE,
            ),
        )

        new_weight = _bounded_weight(
            baseline,
            current,
            requested,
        )

        if (
            abs(
                new_weight - current
            )
            < 1e-9
        ):
            continue

        market_state[
            "weights"
        ][factor] = new_weight

        changes.append(
            {
                "factor": factor,
                "old": round(
                    current,
                    6,
                ),
                "new": round(
                    new_weight,
                    6,
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
            }
        )

    return changes


def _adapt_calibration(
    market_state: dict,
    calibration: dict,
) -> dict | None:
    gap = calibration.get("gap")

    if gap is None:
        return None

    current = float(
        market_state.get(
            "calibration_multiplier",
            1.0,
        )
    )

    requested = max(
        -MAX_CALIBRATION_CHANGE_PER_CYCLE,
        min(
            MAX_CALIBRATION_CHANGE_PER_CYCLE,
            -float(gap) * 0.25,
        ),
    )

    candidate = current * (
        1.0 + requested
    )

    candidate = max(
        MIN_CALIBRATION_MULTIPLIER,
        min(
            MAX_CALIBRATION_MULTIPLIER,
            candidate,
        ),
    )

    if (
        abs(candidate - current)
        < 1e-9
    ):
        return None

    market_state[
        "calibration_multiplier"
    ] = candidate

    return {
        "old": round(
            current,
            6,
        ),
        "new": round(
            candidate,
            6,
        ),
        "mean_confidence":
            calibration[
                "mean_confidence"
            ],
        "accuracy":
            calibration["accuracy"],
        "gap":
            calibration["gap"],
    }


def update_learning_state(
    state: dict | None,
    samples: list[dict],
    *,
    now: datetime | None = None,
) -> tuple[dict, list[dict]]:
    """Evaluate samples and perform bounded market-level adaptation."""
    learning = normalize_learning_state(
        state
    )

    if now is None:
        now = datetime.now(UTC)

    now = timestamp(now)
    now_iso = now.isoformat()

    events = []

    for market in MARKETS:
        rows = [
            row
            for row in samples
            if row.get("market")
            == market
        ]

        rows.sort(
            key=lambda row: (
                timestamp(
                    row["settled_at"]
                ),
                row["fixture_id"],
            )
        )

        market_state = learning[
            "markets"
        ][market]

        total = len(rows)
        # A settled fixture is immutable in the production ledger. Count,
        # latest fixture id and settlement time together identify newly
        # available evidence without tying adaptation to scheduler runs.
        sample_key = (
            f"{total}:{rows[-1]['fixture_id']}:{rows[-1]['settled_at']}"
            if rows else None
        )

        correct = sum(
            1
            for row in rows
            if row["correct"]
        )

        wrong = total - correct

        market_state[
            "total_samples"
        ] = total

        market_state[
            "total_correct"
        ] = correct

        market_state[
            "total_wrong"
        ] = wrong

        market_state[
            "season_accuracy"
        ] = (
            correct / total
            if total
            else None
        )

        recent_20 = _window_stats(
            rows,
            RECENT_REVIEW_WINDOW,
        )

        recent_30 = _window_stats(
            rows,
            RECENT_ADAPT_WINDOW,
        )

        calibration = (
            _calibration_stats(
                rows[
                    -RECENT_ADAPT_WINDOW:
                ]
            )
        )

        market_state[
            "recent_20"
        ] = recent_20

        market_state[
            "recent_30"
        ] = recent_30

        market_state["recent_20_error_rate"] = recent_20["error_rate"]
        market_state["recent_30_error_rate"] = recent_30["error_rate"]

        market_state[
            "calibration"
        ] = calibration

        observation_complete = (
            len(rows) >= 2
            and timestamp(rows[-1]["settled_at"]) - timestamp(rows[0]["settled_at"])
            >= MIN_OBSERVATION_PERIOD
        )

        if not observation_complete or total < MIN_REVIEW_SAMPLES:
            market_state["status"] = "collecting_4_weeks"
            continue

        error_20 = (
            recent_20[
                "error_rate"
            ]
            or 0.0
        )

        if (
            error_20
            < REVIEW_ERROR_RATE
        ):
            market_state[
                "status"
            ] = "normal"
            continue

        market_state[
            "status"
        ] = "review"

        if market_state.get("last_review_sample_key") != sample_key:
            market_state["last_review_at"] = now_iso
            market_state["last_review_sample_key"] = sample_key
            events.append({
                "at": now_iso,
                "market": market,
                "type": "review",
                "samples": total,
                "recent_20_error_rate": error_20,
                "season_accuracy": market_state["season_accuracy"],
                "reason": "recent_20_error_rate_at_or_above_35_percent",
            })

        if total < MIN_ADAPT_SAMPLES:
            continue

        error_30 = (
            recent_30[
                "error_rate"
            ]
            or 0.0
        )

        if (
            error_30
            < ADAPT_ERROR_RATE
        ):
            continue

        critical = (
            error_30
            >= CRITICAL_ERROR_RATE
        )

        market_state[
            "status"
        ] = (
            "critical"
            if critical
            else "adapting"
        )

        # Re-running the same settled sample set must not change the model.
        # This is essential because scheduled learn runs often find no new
        # results for several consecutive days.
        if market_state.get("last_adapted_sample_key") == sample_key:
            continue

        factor_changes = (
            _adapt_factors(
                market_state,
                rows[
                    -RECENT_ADAPT_WINDOW:
                ],
            )
        )

        calibration_change = (
            _adapt_calibration(
                market_state,
                calibration,
            )
        )

        market_state["last_adapted_at"] = now_iso
        market_state["last_adapted_sample_key"] = sample_key

        adaptation_event = {
            "at": now_iso,
            "market": market,
            "type": (
                "critical_adaptation"
                if critical
                else "adaptation"
            ),
            "samples": total,
            "recent_20_error_rate":
                error_20,
            "recent_30_error_rate":
                error_30,
            "season_accuracy":
                market_state[
                    "season_accuracy"
                ],
            "factor_changes":
                factor_changes,
            "calibration_change":
                calibration_change,
            "reason": (
                (
                    "recent_30_error_rate_"
                    "at_or_above_50_percent"
                )
                if critical
                else (
                    "recent_30_error_rate_"
                    "at_or_above_40_percent"
                )
            ),
        }

        events.append(
            adaptation_event
        )

    if events:
        learning["audit"].extend(
            events
        )

        learning["audit"] = (
            learning["audit"][-500:]
        )

    learning[
        "updated_at"
    ] = now_iso

    return learning, events
