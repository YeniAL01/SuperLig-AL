"""
Shared prediction domain models.

Sprint 1 introduces multiple prediction engines that work together
through a common interface. These models are intentionally independent
from app.models to avoid circular imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(slots=True, frozen=True)
class TeamStrength:
    """
    Normalized team statistics used by every prediction engine.
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
    Prediction produced by a single engine.
    """

    engine: str
    home_goals: int
    away_goals: int
    probability: float
    confidence: float
    weight: float
    explanation: str


@dataclass(slots=True)
class EnsembleResult:
    """
    Final prediction after combining every engine.
    """

    home_goals: int
    away_goals: int
    probability: float
    confidence: float
    winner: str
    explanations: List[str] = field(default_factory=list)
    engine_scores: Dict[str, float] = field(default_factory=dict)
    engine_weights: Dict[str, float] = field(default_factory=dict)


@dataclass(slots=True)
class WeightProfile:
    """
    Dynamic weights used by the ensemble engine.
    """

    poisson: float = 1.0
    elo: float = 1.0
    form: float = 1.0
    xg: float = 1.0

    def normalize(self) -> "WeightProfile":
        """
        Normalize weights so that their total equals 1.
        """

        total = self.poisson + self.elo + self.form + self.xg

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

    def as_dict(self) -> Dict[str, float]:
        """
        Export weights as a dictionary.
        """

        return {
            "poisson": self.poisson,
            "elo": self.elo,
            "form": self.form,
            "xg": self.xg,
        }
