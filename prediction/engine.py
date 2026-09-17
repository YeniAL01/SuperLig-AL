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


def outcome(
    home: int,
    away: int,
) -> str:
    if home > away:
        return "HOME"

    if away > home:
        return "AWAY"

    return "DRAW"


def score_grid(
    home_rate: float,
    away_rate: float,
) -> dict:
    """Create a normalized Poisson score grid."""
    grid = {
        (home_goals, away_goals): (
            exp(
                -home_rate
                - away_rate
            )
            * home_rate ** home_goals
            / factorial(home_goals)
            * away_rate ** away_goals
            / factorial(away_goals)
        )
        for home_goals in range(16)
        for away_goals in range(16)
    }

    total = sum(
        grid.values()
    )

    if total <= 0:
        raise ValueError(
            "Invalid score probability grid"
        )

    return {
        score: probability / total
        for score, probability
        in grid.items()
    }


def probabilities(
    grid: dict,
) -> dict:
    """Aggregate a score grid into HOME/DRAW/AWAY probabilities."""
    return {
        label: sum(
            probability
            for (
                home_goals,
                away_goals,
            ), probability
            in grid.items()
            if outcome(
                home_goals,
                away_goals,
            )
            == label
        )
        for label in LABELS
    }


def _expected_rates(
    home: TeamForm,
    away: TeamForm,
) -> tuple[float, float]:
    """Build conservative expected goal rates from pre-match form."""
    def shrink(
        value: float,
        samples: int,
    ) -> float:
        return (
            value * samples
            + 1.35 * 5
        ) / (
            samples + 5
        )

    home_scored = shrink(
        home.scored,
        home.samples,
    )

    home_conceded = shrink(
        home.conceded,
        home.samples,
    )

    away_scored = shrink(
        away.scored,
        away.samples,
    )

    away_conceded = shrink(
        away.conceded,
        away.samples,
    )

    home_rate = max(
        0.2,
        min(
            4.5,
            (
                home_scored
                + away_conceded
            )
            / 2
            + 0.18,
        ),
    )

    away_rate = max(
        0.2,
        min(
            4.5,
            (
                away_scored
                + home_conceded
            )
            / 2,
        ),
    )

    return (
        home_rate,
        away_rate,
    )


def _elo_probabilities(
    home: TeamForm,
    away: TeamForm,
) -> dict:
    """Return HOME/DRAW/AWAY probabilities from Elo ratings."""
    expected = 1 / (
        1
        + 10 ** (
            (
                away.elo
                - home.elo
                - 65
            )
            / 400
        )
    )

    draw = (
        0.28
        * exp(
            -abs(
                home.elo
                - away.elo
            )
            / 800
        )
    )

    return {
        "HOME": (
            1 - draw
        ) * expected,
        "DRAW": draw,
        "AWAY": (
            1 - draw
        ) * (
            1 - expected
        ),
    }


def _xg_probabilities(
    home: TeamForm,
    away: TeamForm,
) -> dict | None:
    """Return xG-based probabilities only when enough valid data exists."""
    if (
        home.samples < 5
        or away.samples < 5
    ):
        return None

    values = (
        home.expected_goals,
        home.expected_goals_against,
        away.expected_goals,
        away.expected_goals_against,
    )

    if any(
        value is None
        for value in values
    ):
        return None

    home_rate = max(
        0.2,
        min(
            4.5,
            (
                float(
                    home.expected_goals
                )
                + float(
                    away.expected_goals_against
                )
            )
            / 2
            + 0.18,
        ),
    )

    away_rate = max(
        0.2,
        min(
            4.5,
            (
                float(
                    away.expected_goals
                )
                + float(
                    home.expected_goals_against
                )
            )
            / 2,
        ),
    )

    return probabilities(
        score_grid(
            home_rate,
            away_rate,
        )
    )


def _normalize_probabilities(
    probs: dict,
) -> dict:
    """Protect persisted forecasts from floating-point drift."""
    cleaned = {
        label: max(
            0.0,
            float(
                probs.get(
                    label,
                    0.0,
                )
            ),
        )
        for label in LABELS
    }

    total = sum(
        cleaned.values()
    )

    if total <= 0:
        return {
            label: 1.0 / len(
                LABELS
            )
            for label in LABELS
        }

    return {
        label: (
            cleaned[label]
            / total
        )
        for label in LABELS
    }


class PredictionEngine:
    """Generate immutable adaptive-v2 pre-match predictions."""

    def __init__(
        self,
        records: list | None = None,
    ) -> None:
        self.records = (
            records
            if records is not None
            else []
        )

    def predict(
        self,
        fixture: Fixture,
        home: TeamForm,
        away: TeamForm,
        confidence: float = 0,
        lineup_verified: bool = False,
        as_of: datetime | None = None,
    ) -> Prediction:
        """Create one forecast using only information available pre-kickoff."""
        # Legacy confidence is deliberately accepted for compatibility,
        # but it must never override the model probability.
        _ = confidence

        as_of = (
            as_of
            or datetime.now(UTC)
        )

        if as_of.tzinfo is None:
            raise ValueError(
                "Prediction timestamp must "
                "be timezone-aware"
            )

        if as_of >= fixture.start:
            raise ValueError(
                "Forecast must be created "
                "before kickoff"
            )

        home_rate, away_rate = (
            _expected_rates(
                home,
                away,
            )
        )

        grid = score_grid(
            home_rate,
            away_rate,
        )

        poisson = probabilities(
            grid
        )

        components = {
            "poisson": poisson,
            "elo": _elo_probabilities(
                home,
                away,
            ),
            "baseline": {
                "HOME": 0.45,
                "DRAW": 0.27,
                "AWAY": 0.28,
            },
        }

        xg = _xg_probabilities(
            home,
            away,
        )

        if xg is not None:
            components["xg"] = xg

        # Existing adaptive-v2 learning remains authoritative here.
        # It learns which probability experts have historically been
        # better calibrated using settled pre-match forecasts.
        weights = model_weights(
            self.records,
            list(
                components
            ),
            as_of,
        )

        combined = {
            label: sum(
                weights[name]
                * component[label]
                for name, component
                in components.items()
            )
            for label in LABELS
        }

        probs = (
            _normalize_probabilities(
                combined
            )
        )

        winner = max(
            probs,
            key=probs.get,
        )

        # Reweight the original score grid so the selected score remains
        # consistent with the selected 1X2 outcome.
        joint = {}

        for score, probability in (
            grid.items()
        ):
            score_outcome = outcome(
                *score
            )

            denominator = poisson[
                score_outcome
            ]

            if denominator <= 0:
                continue

            joint[score] = (
                probability
                * probs[
                    score_outcome
                ]
                / denominator
            )

        compatible_scores = [
            score
            for score in joint
            if outcome(
                *score
            )
            == winner
        ]

        if not compatible_scores:
            raise ValueError(
                "No score compatible with "
                "predicted outcome"
            )

        score = max(
            compatible_scores,
            key=joint.get,
        )

        confidence_value = round(
            100
            * probs[winner],
            2,
        )

        return Prediction(
            fixture.id,
            (
                f"{fixture.home} - "
                f"{fixture.away}"
            ),
            {
                "HOME":
                    fixture.home,
                "AWAY":
                    fixture.away,
                "DRAW":
                    "Beraberlik",
            }[winner],
            score[0],
            score[1],
            confidence_value,
            lineup_verified,
            note=(
                "Model olasılığıdır; "
                "gerçek başarı garantisi değildir. "
                "Skor, seçilen maç sonucuyla "
                "uyumlu en olası skordur."
            ),
            probabilities=probs,
            component_probabilities=
                components,
            model_weights=weights,
            kickoff=
                fixture.start.isoformat(),
            created_at=
                as_of.isoformat(),
            home_team=
                fixture.home,
            away_team=
                fixture.away,
            outcome=winner,
            data_quality=min(
                1.0,
                min(
                    home.samples,
                    away.samples,
                )
                / 10,
            ),
            model_version=
                "adaptive-v2",
            score_probability=
                joint[score],
        )
