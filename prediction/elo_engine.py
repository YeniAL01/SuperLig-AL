"""
Elo based prediction engine.

Sprint 1

This engine estimates the expected match result using the Elo rating
difference between both teams.

The result of this engine is later combined with Poisson, Form and xG
inside the EnsembleDecisionEngine.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp

from prediction.models import EnginePrediction


@dataclass(slots=True, frozen=True)
class EloTeam:
    """
    Elo information required by the prediction engine.
    """

    name: str
    rating: float


class EloEngine:
    """
    Calculates score expectations using the Elo model.

    This class never returns the final prediction.
    It only produces one opinion for the ensemble.
    """

    HOME_ADVANTAGE = 75.0

    def predict(
        self,
        home: EloTeam,
        away: EloTeam,
    ) -> EnginePrediction:
        """
        Produce an Elo based prediction.

        Parameters
        ----------
        home:
            Home team Elo data.

        away:
            Away team Elo data.

        Returns
        -------
        EnginePrediction
        """

        expected_home = self._expected_score(
            home.rating + self.HOME_ADVANTAGE,
            away.rating,
        )

        expected_away = 1.0 - expected_home

        home_goals = self._estimate_goals(expected_home)
        away_goals = self._estimate_goals(expected_away)

        probability = max(expected_home, expected_away)

        confidence = 45.0 + probability * 40.0

        winner = (
            home.name
            if home_goals > away_goals
            else away.name
            if away_goals > home_goals
            else "Draw"
        )

        explanation = (
            f"Elo difference predicts {winner} "
            f"(home={expected_home:.3f}, away={expected_away:.3f})"
        )

        return EnginePrediction(
            engine="elo",
            home_goals=home_goals,
            away_goals=away_goals,
            probability=round(probability, 4),
            confidence=round(min(confidence, 95.0), 2),
            weight=1.0,
            explanation=explanation,
        )

    @staticmethod
    def _expected_score(
        rating_a: float,
        rating_b: float,
    ) -> float:
        """
        Calculate Elo expected score.
        """

        return 1.0 / (
            1.0
            + 10 ** ((rating_b - rating_a) / 400.0)
        )

    @staticmethod
    def _estimate_goals(
        expected_score: float,
    ) -> int:
        """
        Convert expected score into an expected goal count.

        The mapping is intentionally conservative because
        the final score will be decided by the ensemble.
        """

        if expected_score >= 0.82:
            return 3

        if expected_score >= 0.65:
            return 2

        if expected_score >= 0.45:
            return 1

        return 0

    @staticmethod
    def calibration_factor(
        rating_difference: float,
    ) -> float:
        """
        Produce a calibration value between 0 and 1.

        This value will later be consumed by the
        Dynamic Weight Engine.
        """

        value = 1.0 - exp(-abs(rating_difference) / 300.0)

        return round(min(max(value, 0.0), 1.0), 4)
