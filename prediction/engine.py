"""Explainable Poisson ensemble for match score forecasts."""
from __future__ import annotations
from dataclasses import dataclass
from math import exp, factorial
from app.models import Fixture, Prediction

@dataclass(frozen=True, slots=True)
class TeamForm:
    """Normalized team indicators collected before a match."""
    scored: float
    conceded: float
    form_points: float
    samples: int

class PredictionEngine:
    """Combines attack, defence, form and home advantage into score probabilities."""
    def predict(self, fixture: Fixture, home: TeamForm, away: TeamForm, confidence: float, lineup_verified: bool) -> Prediction:
        """Choose the most likely score from a bounded Poisson score grid."""
        home_lambda = max(0.2, min(3.5, (home.scored + away.conceded) / 2 + 0.18 + (home.form_points - away.form_points) * 0.06))
        away_lambda = max(0.2, min(3.5, (away.scored + home.conceded) / 2 - (home.form_points - away.form_points) * 0.06))
        score, probability = max(
            (((h, a), self._poisson(h, home_lambda) * self._poisson(a, away_lambda)) for h in range(6) for a in range(6)),
            key=lambda item: item[1],
        )
        winner = fixture.home if score[0] > score[1] else fixture.away if score[1] > score[0] else "Beraberlik"
        return Prediction(fixture.id, f"{fixture.home} - {fixture.away}", winner, score[0], score[1], confidence, lineup_verified, "")

    @staticmethod
    def _poisson(goals: int, rate: float) -> float:
        """Calculate a Poisson probability."""
        return exp(-rate) * rate**goals / factorial(goals)
