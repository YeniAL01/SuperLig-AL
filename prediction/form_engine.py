"""
Recent form prediction engine.

Sprint 1

Evaluates recent team performance independent of Poisson and Elo.
The output becomes one vote inside the Ensemble Decision Engine.
"""

from __future__ import annotations

from dataclasses import dataclass

from prediction.models import EnginePrediction


@dataclass(slots=True, frozen=True)
class FormTeam:
    """
    Recent team statistics.
    """

    name: str
    points_per_match: float
    goals_scored: float
    goals_conceded: float
    unbeaten_streak: int
    wins_last_five: int


class FormEngine:
    """
    Estimates match outcome using only recent form.
    """

    def predict(
        self,
        home: FormTeam,
        away: FormTeam,
    ) -> EnginePrediction:

        home_strength = self._strength(home)
        away_strength = self._strength(away)

        difference = home_strength - away_strength

        if difference >= 0.60:
            score = (3, 1)

        elif difference >= 0.30:
            score = (2, 1)

        elif difference >= 0.10:
            score = (1, 0)

        elif difference <= -0.60:
            score = (1, 3)

        elif difference <= -0.30:
            score = (1, 2)

        elif difference <= -0.10:
            score = (0, 1)

        else:
            score = (1, 1)

        probability = min(
            0.92,
            0.50 + abs(difference) * 0.35,
        )

        confidence = min(
            95.0,
            48.0 + abs(difference) * 35.0,
        )

        winner = (
            home.name
            if score[0] > score[1]
            else away.name
            if score[1] > score[0]
            else "Beraberlik"
        )

        return EnginePrediction(
            engine="form",
            fixture_id=0,
            fixture_name=f"{home.name} - {away.name}",
            home_goals=score[0],
            away_goals=score[1],
            probability=round(probability, 4),
            confidence=round(confidence, 2),
            weight=1.0,
            explanation=(
                f"Recent form favours {winner}. "
                f"Strength difference={difference:.3f}"
            ),
        )

    @staticmethod
    def _strength(team: FormTeam) -> float:
        """
        Calculate normalized form strength.
        """

        attack = team.goals_scored * 0.30

        defence = max(
            0.0,
            (3.0 - team.goals_conceded) * 0.25,
        )

        ppm = team.points_per_match * 0.20

        unbeaten = min(
            team.unbeaten_streak,
            10,
        ) * 0.04

        recent = team.wins_last_five * 0.10

        return (
            attack
            + defence
            + ppm
            + unbeaten
            + recent
        )

    @staticmethod
    def consistency_score(
        team: FormTeam,
    ) -> float:
        """
        Returns a normalized consistency value (0-1).

        Used later by the Dynamic Weight Engine.
        """

        value = (
            team.points_per_match / 3.0
            + min(team.unbeaten_streak, 10) / 10.0
        ) / 2.0

        return round(
            max(0.0, min(value, 1.0)),
            4,
        )
