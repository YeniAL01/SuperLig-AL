"""Probabilistic forecasts using evidence available before kickoff."""

from dataclasses import dataclass
from datetime import UTC, datetime
from math import exp, factorial

from app.models import Fixture, Prediction
from learning.adaptive import (
    calibrated_confidence,
    factor_snapshot,
    market_learning,
    model_weights,
)


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
    """Aggregate score probabilities into HOME/DRAW/AWAY."""
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


def ou25_probabilities(
    grid: dict,
) -> dict:
    """Calculate Over/Under 2.5 probabilities."""
    over = sum(
        probability
        for (
            home_goals,
            away_goals,
        ), probability
        in grid.items()
        if home_goals + away_goals >= 3
    )

    under = sum(
        probability
        for (
            home_goals,
            away_goals,
        ), probability
        in grid.items()
        if home_goals + away_goals <= 2
    )

    total = over + under

    if total <= 0:
        return {
            "OVER": 0.5,
            "UNDER": 0.5,
        }

    return {
        "OVER": over / total,
        "UNDER": under / total,
    }


def btts_probabilities(
    grid: dict,
) -> dict:
    """Calculate both-teams-to-score probabilities."""
    yes = sum(
        probability
        for (
            home_goals,
            away_goals,
        ), probability
        in grid.items()
        if home_goals > 0
        and away_goals > 0
    )

    no = sum(
        probability
        for (
            home_goals,
            away_goals,
        ), probability
        in grid.items()
        if home_goals == 0
        or away_goals == 0
    )

    total = yes + no

    if total <= 0:
        return {
            "YES": 0.5,
            "NO": 0.5,
        }

    return {
        "YES": yes / total,
        "NO": no / total,
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
    """Return xG probabilities only when enough valid data exists."""
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


def _form_signal(
    home: TeamForm,
    away: TeamForm,
) -> float:
    difference = (
        home.form_points
        - away.form_points
    )

    return max(
        -1.0,
        min(
            1.0,
            difference / 3.0,
        ),
    )


def _elo_signal(
    home: TeamForm,
    away: TeamForm,
) -> float:
    return max(
        -1.0,
        min(
            1.0,
            (
                home.elo
                - away.elo
            )
            / 400.0,
        ),
    )


def _goals_signal(
    home_rate: float,
    away_rate: float,
) -> float:
    return max(
        -1.0,
        min(
            1.0,
            (
                home_rate
                + away_rate
                - 2.5
            )
            / 2.5,
        ),
    )


def _availability_signal(
    home: TeamForm,
    away: TeamForm,
) -> float:
    minimum_samples = min(
        home.samples,
        away.samples,
    )

    return max(
        0.0,
        min(
            1.0,
            minimum_samples / 10.0,
        ),
    )


def _model_signal(
    probs: dict,
) -> float:
    values = sorted(
        (
            float(value)
            for value
            in probs.values()
        ),
        reverse=True,
    )

    if len(values) < 2:
        return 0.0

    return max(
        0.0,
        min(
            1.0,
            values[0] - values[1],
        ),
    )


def _build_factor_snapshot(
    home: TeamForm,
    away: TeamForm,
    home_rate: float,
    away_rate: float,
    lineup_verified: bool,
    probs: dict,
) -> dict:
    """Create factors using only evidence actually available."""
    return factor_snapshot(
        form=_form_signal(
            home,
            away,
        ),
        home_away=0.18,
        elo=_elo_signal(
            home,
            away,
        ),
        goals=_goals_signal(
            home_rate,
            away_rate,
        ),
        lineup=(
            1.0
            if lineup_verified
            else 0.0
        ),
        availability=_availability_signal(
            home,
            away,
        ),
        # No verified odds provider is connected here.
        # Neutral zero means odds cannot influence the forecast.
        odds_support=0.0,
        model_signal=_model_signal(
            probs
        ),
    )


def _market_payload(
    probabilities_map: dict,
    learning_state: dict | None,
    market: str,
    factors: dict,
) -> dict:
    """Build one immutable market prediction snapshot."""
    selection = max(
        probabilities_map,
        key=probabilities_map.get,
    )

    raw_confidence = (
        float(
            probabilities_map[
                selection
            ]
        )
        * 100.0
    )

    state = market_learning(
        learning_state,
        market,
    )

    confidence = calibrated_confidence(
        raw_confidence,
        state,
    )

    return {
        "selection": selection,
        "confidence": round(
            confidence,
            2,
        ),
        "raw_confidence": round(
            raw_confidence,
            2,
        ),
        "probabilities": {
            key: float(value)
            for key, value
            in probabilities_map.items()
        },
        "factors": dict(
            factors
        ),
        "learning_status": state.get(
            "status",
            "collecting",
        ),
        "learning_samples": int(
            state.get(
                "total_samples",
                0,
            )
            or 0
        ),
    }


class PredictionEngine:
    """Generate immutable adaptive-v2 pre-match predictions."""

    def __init__(
        self,
        records: list | None = None,
        learning_state: dict | None = None,
    ) -> None:
        self.records = (
            records
            if records is not None
            else []
        )

        self.learning_state = (
            learning_state
            if isinstance(
                learning_state,
                dict,
            )
            else {}
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
        # Accepted only for backward compatibility.
        # Model probabilities remain authoritative.
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

        base_grid = score_grid(
            home_rate,
            away_rate,
        )

        poisson = probabilities(
            base_grid
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
            components[
                "xg"
            ] = xg

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

        probs = _normalize_probabilities(
            combined
        )

        winner = max(
            probs,
            key=probs.get,
        )

        # Reweight the Poisson score grid so that the score distribution
        # remains consistent with the adaptive 1X2 probabilities.
        joint = {}

        for score, probability in (
            base_grid.items()
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

        joint_total = sum(
            joint.values()
        )

        if joint_total <= 0:
            raise ValueError(
                "Invalid adaptive score distribution"
            )

        joint = {
            score: probability
            / joint_total
            for score, probability
            in joint.items()
        }

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

        ou25 = ou25_probabilities(
            joint
        )

        btts = btts_probabilities(
            joint
        )

        factors = _build_factor_snapshot(
            home,
            away,
            home_rate,
            away_rate,
            lineup_verified,
            probs,
        )

        markets = {
            "1x2": _market_payload(
                probs,
                self.learning_state,
                "1x2",
                factors,
            ),
            "ou25": _market_payload(
                ou25,
                self.learning_state,
                "ou25",
                factors,
            ),
            "btts": _market_payload(
                btts,
                self.learning_state,
                "btts",
                factors,
            ),
        }

        # Keep the legacy top-level confidence synchronized with the
        # calibrated 1X2 confidence because publishability currently
        # evaluates Prediction.confidence.
        confidence_value = float(
            markets[
                "1x2"
            ][
                "confidence"
            ]
        )

        # build_learning_samples() supports factor snapshots indexed
        # directly by market. Each market gets an immutable copy.
        factor_snapshots = {
            market: dict(
                factors
            )
            for market in (
                "1x2",
                "ou25",
                "btts",
            )
        }

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
            component_probabilities=components,
            model_weights=weights,
            kickoff=fixture.start.isoformat(),
            created_at=as_of.isoformat(),
            home_team=fixture.home,
            away_team=fixture.away,
            outcome=winner,
            data_quality=min(
                1.0,
                min(
                    home.samples,
                    away.samples,
                )
                / 10,
            ),
            model_version="adaptive-v2",
            score_probability=joint[
                score
            ],
            markets=markets,
            factor_snapshot=factor_snapshots,
        )
