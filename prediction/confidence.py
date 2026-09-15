"""Confidence scoring and publication threshold."""
from dataclasses import dataclass
from prediction.engine import TeamForm

@dataclass(frozen=True, slots=True)
class ConfidenceEngine:
    """Scores data quality without pretending uncertainty is certainty."""
    minimum_to_publish: float = 58.0
    def calculate(self, home: TeamForm, away: TeamForm, lineup_verified: bool, calibration: float) -> float:
        """Calculate bounded confidence from coverage, lineups and calibration."""
        coverage = min(1.0, (home.samples + away.samples) / 20)
        score = 35 + coverage * 25 + calibration * 20 + (15 if lineup_verified else -8)
        return round(max(0.0, min(95.0, score)), 1)
