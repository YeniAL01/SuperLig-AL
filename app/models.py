"""Domain data structures."""
from dataclasses import dataclass, asdict, field
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
    """An immutable published prediction."""
    fixture_id: int
    fixture: str
    winner: str
    home_goals: int
    away_goals: int
    confidence: float
    lineup_verified: bool
    note: str = ""
    probabilities: dict = field(default_factory=dict)
    component_probabilities: dict = field(default_factory=dict)
    model_weights: dict = field(default_factory=dict)
    kickoff: str = ""
    created_at: str = ""
    home_team: str = ""
    away_team: str = ""
    outcome: str = ""
    data_quality: float = 0.0
    model_version: str = "legacy"
    score_probability: float = 0.0

    def payload(self) -> dict[str, object]:
        """Convert to JSON-compatible data."""
        return asdict(self)
