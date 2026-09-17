"""
Expected Goals (xG) prediction engine.

Uses attacking and defensive expected goal values
to generate an independent prediction.

This engine does not make the final decision.
Its output is consumed by the Ensemble Engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from prediction.models import EnginePrediction


@dataclass(slots=True, frozen=True)
class XGTeam:
    """
    Expected goal statistics.
    """

    name: str

    expected_goals_for: float

    expected_goals_against: float

    shots_on_target: float

    big_chances: float

    conversion_rate: float


class XGEngine:
    """
    Predicts match score using expected goals.
    """

    HOME_ADVANTAGE = 0.15

    def predict(
        self,
        home: XGTeam,
        away: XGTeam,
    ) -> EnginePrediction:

        home_attack = (
            home.expected_goals_for
            + self.HOME_ADVANTAGE
        )

        away_attack = away.expected_goals_for

        home_defence = away.expected_goals_against

        away_defence = home.expected_goals_against

        home_rating = (
            home_attack
            + home.shots_on_target * 0.10
            + home.big_chances * 0.12
            + home.conversion_rate
        ) - home_defence

        away_rating = (
            away_attack
            + away.shots_on_target * 0.10
            + away.big_chances * 0.12
            + away.conversion_rate
        ) - away_defence

        difference = home_rating - away_rating

        score = self._estimate_score(difference)

        probability = min(
            0.95,
            0.50 + abs(difference) * 0.25,
        )

        confidence = min(
            95.0,
            50.0 + abs(difference) * 30.0,
        )

        winner = (
            home.name
            if score[0] > score[1]
            else away.name
            if score[1] > score[0]
            else "Beraberlik"
        )

        return EnginePrediction(
            engine="xg",
            home_goals=score[0],
            away_goals=score[1],
            probability=round(probability, 4),
            confidence=round(confidence, 2),
            weight=1.0,
            explanation=(
                f"xG model favours {winner}. "
                f"Difference={difference:.3f}"
            ),
        )

    @staticmethod
    def _estimate_score(
        difference: float,
    ) -> tuple[int, int]:

        if difference >= 1.20:
            return 3, 1

        if difference >= 0.70:
            return 2, 0

        if difference >= 0.30:
            return 2, 1

        if difference >= 0.10:
            return 1, 0

        if difference <= -1.20:
            return 1, 3

        if difference <= -0.70:
            return 0, 2

        if difference <= -0.30:
            return 1, 2

        if difference <= -0.10:
            return 0, 1

        return 1, 1

    @staticmethod
    def quality_score(
        team: XGTeam,
    ) -> float:
        """
        Returns a normalized data quality value (0-1).

        Used later by the Dynamic Weight Engine.
        """

        value = (
            team.expected_goals_for
            + team.shots_on_target * 0.20
            + team.big_chances * 0.15
        ) / 4.5

        return round(
            max(0.0, min(value, 1.0)),
            4,
        )
