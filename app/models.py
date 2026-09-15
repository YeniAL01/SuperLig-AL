"""Domain data structures."""
from dataclasses import dataclass, asdict
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

    def payload(self) -> dict[str, object]:
        """Convert to JSON-compatible data."""
        return asdict(self)
