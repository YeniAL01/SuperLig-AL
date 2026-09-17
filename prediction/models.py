"""
Shared prediction domain models.

Sprint 1

Shared data contracts used by every prediction engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict
from typing import List


@dataclass(slots=True, frozen=True)
class TeamStrength:
    """
    Normalized team statistics.
    """

    attack: float

    defence: float

    form: float

    expected_goals: float

    elo_rating: float

    home_advantage: float = 0.18


@dataclass(slots=True, frozen=True)
class EnginePrediction:
    """
    Prediction produced by one prediction engine.
    """

    engine: str

    fixture_id: int

    fixture_name: str

    home_goals: int

    away_goals: int

    probability: float

    confidence: float

    weight: float

    explanation: str

    @property
    def winner(self) -> str:

        if self.home_goals > self.away_goals:
            return "HOME"

        if self.away_goals > self.home_goals:
            return "AWAY"

        return "DRAW"

    @property
    def score(self) -> tuple[int, int]:
        return (
            self.home_goals,
            self.away_goals,
        )


@dataclass(slots=True)
class EnsembleResult:
    """
    Final ensemble prediction.
    """

    fixture_id: int

    fixture_name: str

    home_goals: int

    away_goals: int

    probability: float

    confidence: float

    winner: str

    explanations: List[str] = field(
        default_factory=list,
    )

    engine_scores: Dict[str, float] = field(
        default_factory=dict,
    )

    engine_weights: Dict[str, float] = field(
        default_factory=dict,
    )

    votes: Dict[str, float] = field(
        default_factory=dict,
    )

    @property
    def score(self) -> tuple[int, int]:
        return (
            self.home_goals,
            self.away_goals,
        )


@dataclass(slots=True)
class WeightProfile:
    """
    Dynamic ensemble weights.
    """

    poisson: float = 1.0

    elo: float = 1.0

    form: float = 1.0

    xg: float = 1.0

    def normalize(
        self,
    ) -> "WeightProfile":

        total = (
            self.poisson
            + self.elo
            + self.form
            + self.xg
        )

        if total <= 0:

            self.poisson = 0.25
            self.elo = 0.25
            self.form = 0.25
            self.xg = 0.25

            return self

        self.poisson /= total
        self.elo /= total
        self.form /= total
        self.xg /= total

        return self

    @property
    def total(self) -> float:
        return (
            self.poisson
            + self.elo
            + self.form
            + self.xg
        )

    def as_dict(
        self,
    ) -> Dict[str, float]:

        return {
            "poisson": self.poisson,
            "elo": self.elo,
            "form": self.form,
            "xg": self.xg,
        }
