"""Domain data structures."""

from dataclasses import asdict, dataclass, field
from datetime import datetime


@dataclass(frozen=True, slots=True)
class Fixture:
    """A scheduled Super Lig fixture."""

    id: int
    home: str
    away: str
    start: datetime
    venue: str = ""


@dataclass(frozen=True, slots=True)
class Prediction:
    """An immutable pre-match prediction."""

    fixture_id: int
    fixture: str
    winner: str
    home_goals: int
    away_goals: int
    confidence: float
    lineup_verified: bool

    note: str = ""

    # Existing 1X2 probability model.
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
    model_version: str = "legacy"
    score_probability: float = 0.0

    # --------------------------------------------------------------
    # Multi-market prediction snapshot.
    #
    # Structure:
    #
    # {
    #     "1x2": {
    #         "selection": "HOME",
    #         "confidence": 54.2,
    #         "probabilities": {
    #             "HOME": 0.542,
    #             "DRAW": 0.251,
    #             "AWAY": 0.207,
    #         },
    #     },
    #     "ou25": {
    #         "selection": "OVER",
    #         "confidence": 58.1,
    #         "probabilities": {
    #             "OVER": 0.581,
    #             "UNDER": 0.419,
    #         },
    #     },
    #     "btts": {
    #         "selection": "YES",
    #         "confidence": 61.3,
    #         "probabilities": {
    #             "YES": 0.613,
    #             "NO": 0.387,
    #         },
    #     },
    # }
    #
    # Default factory keeps old persisted forecasts compatible with
    # Prediction(**row) as long as they do not contain unknown fields.
    # --------------------------------------------------------------
    markets: dict = field(
        default_factory=dict
    )

    # Immutable pre-match factor snapshot used by the learning layer.
    # The learning system may evaluate these factors after settlement,
    # but the historical prediction itself is never rewritten.
    factor_snapshot: dict = field(
        default_factory=dict
    )

    def payload(
        self,
    ) -> dict[str, object]:
        """Convert to JSON-compatible data."""

        return asdict(self)
