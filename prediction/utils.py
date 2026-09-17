"""
Prediction utility functions.

Sprint 1

Shared helper functions used by every prediction engine.

The goal is to keep calculation logic in one place and avoid
duplicated code across prediction engines.
"""

from __future__ import annotations

from math import exp
from typing import Iterable


def clamp(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    """
    Clamp a numeric value.
    """

    return max(minimum, min(value, maximum))


def normalize(
    value: float,
    minimum: float,
    maximum: float,
) -> float:
    """
    Normalize a value between 0 and 1.
    """

    if maximum <= minimum:
        return 0.0

    return clamp(
        (value - minimum) / (maximum - minimum),
        0.0,
        1.0,
    )


def safe_average(
    values: Iterable[float],
) -> float:
    """
    Returns average without raising ZeroDivisionError.
    """

    values = list(values)

    if not values:
        return 0.0

    return sum(values) / len(values)


def weighted_average(
    values: Iterable[float],
    weights: Iterable[float],
) -> float:
    """
    Calculate weighted average.
    """

    values = list(values)
    weights = list(weights)

    if not values:
        return 0.0

    if len(values) != len(weights):
        raise ValueError(
            "Values and weights must have same length."
        )

    total_weight = sum(weights)

    if total_weight <= 0:
        return safe_average(values)

    weighted_sum = sum(
        value * weight
        for value, weight in zip(values, weights)
    )

    return weighted_sum / total_weight


def logistic(
    value: float,
    steepness: float = 1.0,
) -> float:
    """
    Logistic normalization.
    """

    return 1.0 / (
        1.0 + exp(-steepness * value)
    )


def confidence_scale(
    probability: float,
) -> float:
    """
    Convert probability to confidence.

    Sprint 2 will replace this function.
    """

    probability = clamp(
        probability,
        0.0,
        1.0,
    )

    return round(
        35.0 + probability * 60.0,
        2,
    )


def goal_difference(
    home_goals: int,
    away_goals: int,
) -> int:
    """
    Goal difference.
    """

    return home_goals - away_goals


def match_result(
    home_goals: int,
    away_goals: int,
) -> str:
    """
    Returns HOME, AWAY or DRAW.
    """

    if home_goals > away_goals:
        return "HOME"

    if away_goals > home_goals:
        return "AWAY"

    return "DRAW"


def agreement_score(
    votes: Iterable[str],
) -> float:
    """
    Calculates model agreement.

    Returns

    0.0 - 1.0
    """

    votes = list(votes)

    if not votes:
        return 0.0

    counts: dict[str, int] = {}

    for vote in votes:
        counts[vote] = counts.get(vote, 0) + 1

    majority = max(
        counts.values()
    )

    return round(
        majority / len(votes),
        4,
    )


def normalize_weights(
    weights: dict[str, float],
) -> dict[str, float]:
    """
    Normalize weight dictionary.
    """

    total = sum(weights.values())

    if total <= 0:

        equal = 1 / len(weights)

        return {
            key: equal
            for key in weights
        }

    return {
        key: value / total
        for key, value in weights.items()
    }
