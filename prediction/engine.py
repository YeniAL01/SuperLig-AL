"""Probabilistic forecasts using evidence available before kickoff."""
from dataclasses import dataclass
from datetime import UTC, datetime
from math import exp, factorial
from app.models import Fixture, Prediction
from learning.adaptive import model_weights

LABELS = ("HOME", "DRAW", "AWAY")

@dataclass(frozen=True, slots=True)
class TeamForm:
    scored: float
    conceded: float
    form_points: float
    samples: int
    elo: float = 1500.0
    expected_goals: float | None = None
    expected_goals_against: float | None = None
    shots_on_target: float = 0.0
    big_chances: float = 0.0
    conversion_rate: float = 0.0
    unbeaten_streak: int = 0
    wins_last_five: int = 0

def outcome(home: int, away: int) -> str:
    return "HOME" if home > away else "AWAY" if away > home else "DRAW"

def score_grid(home_rate: float, away_rate: float) -> dict:
    grid = {(h, a): exp(-home_rate-away_rate) * home_rate**h / factorial(h)
            * away_rate**a / factorial(a) for h in range(16) for a in range(16)}
    total = sum(grid.values())
    return {s: p / total for s, p in grid.items()}

def probabilities(grid: dict) -> dict:
    return {label: sum(p for (h, a), p in grid.items() if outcome(h, a) == label)
            for label in LABELS}

class PredictionEngine:
    def __init__(self, records: list | None = None) -> None:
        self.records = records or []

    def predict(self, fixture: Fixture, home: TeamForm, away: TeamForm,
                confidence: float = 0, lineup_verified: bool = False,
                as_of: datetime | None = None) -> Prediction:
        # Legacy confidence argument is accepted but cannot override probability.
        as_of = as_of or datetime.now(UTC)
        if as_of >= fixture.start:
            raise ValueError("Forecast must be created before kickoff")
        shrink = lambda value, n: (value * n + 1.35 * 5) / (n + 5)
        hs, hc = shrink(home.scored, home.samples), shrink(home.conceded, home.samples)
        aws, ac = shrink(away.scored, away.samples), shrink(away.conceded, away.samples)
        grid = score_grid(max(.2, min(4.5, (hs+ac)/2+.18)),
                          max(.2, min(4.5, (aws+hc)/2)))
        poisson = probabilities(grid)
        expected = 1 / (1 + 10 ** ((away.elo-home.elo-65) / 400))
        draw = .28 * exp(-abs(home.elo-away.elo) / 800)
        components = {
            "poisson": poisson,
            "elo": {"HOME": (1-draw)*expected, "DRAW": draw, "AWAY": (1-draw)*(1-expected)},
            "baseline": {"HOME": .45, "DRAW": .27, "AWAY": .28},
        }
        if (home.samples >= 5 and away.samples >= 5 and
                all(v is not None for v in (home.expected_goals, home.expected_goals_against,
                                            away.expected_goals, away.expected_goals_against))):
            components["xg"] = probabilities(score_grid(
                max(.2, min(4.5, (home.expected_goals+away.expected_goals_against)/2+.18)),
                max(.2, min(4.5, (away.expected_goals+home.expected_goals_against)/2))))
        weights = model_weights(self.records, list(components), as_of)
        probs = {label: sum(weights[name]*p[label] for name, p in components.items())
                 for label in LABELS}
        winner = max(probs, key=probs.get)
        joint = {s: p * probs[outcome(*s)] / poisson[outcome(*s)] for s, p in grid.items()}
        score = max((s for s in joint if outcome(*s) == winner), key=joint.get)
        return Prediction(
            fixture.id, f"{fixture.home} - {fixture.away}",
            {"HOME": fixture.home, "AWAY": fixture.away, "DRAW": "Beraberlik"}[winner],
            *score, round(100 * probs[winner], 2), lineup_verified,
            note="Model olasılığıdır; gerçek başarı garantisi değildir. "
                 "Skor, seçilen maç sonucuyla uyumlu en olası skordur.",
            probabilities=probs, component_probabilities=components, model_weights=weights,
            kickoff=fixture.start.isoformat(), created_at=as_of.isoformat(),
            home_team=fixture.home, away_team=fixture.away, outcome=winner,
            data_quality=min(1., min(home.samples, away.samples)/10),
            model_version="adaptive-v2", score_probability=joint[score])

