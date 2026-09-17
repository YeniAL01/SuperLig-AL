"""Core immutable application models."""

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Fixture:
    """One scheduled Süper Lig fixture."""

    id: int | str
    home: str
    away: str
    start: datetime


@dataclass(frozen=True, slots=True)
class Prediction:
    """Immutable final pre-match prediction snapshot."""

    fixture_id: int | str
    fixture: str
    winner: str
    home_goals: int
    away_goals: int
    confidence: float
    lineup_verified: bool

    note: str = ""

    probabilities: dict = field(
        default_factory=dict
    )

    component_probabilities: dict = field(
        default_factory=dict
    )

    model_weights: dict = field(
        default_factory=dict
    )

    kickoff: str = ""
    created_at: str = ""

    home_team: str = ""
    away_team: str = ""
    outcome: str = ""

    data_quality: float = 0.0
    model_version: str = ""

    score_probability: float = 0.0

    # Final market snapshots used by Telegram,
    # performance evaluation and adaptive learning.
    #
    # Expected keys:
    #   1x2
    #   ou25
    #   btts
    markets: dict = field(
        default_factory=dict
    )

    # Immutable evidence snapshot captured at prediction time.
    #
    # Expected structure:
    # {
    #     "1x2": {...factors...},
    #     "ou25": {...factors...},
    #     "btts": {...factors...},
    # }
    factor_snapshot: dict = field(
        default_factory=dict
    )

    def payload(
        self,
    ) -> dict:
        """Return a JSON-serializable prediction payload."""
        return asdict(
            self
        )
