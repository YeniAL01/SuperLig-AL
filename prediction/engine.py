"""
Prediction Engine

Sprint 1

Main orchestration layer for all prediction engines.

Pipeline

TeamForm
    ↓
Poisson
    ↓
Elo
    ↓
Form
    ↓
xG
    ↓
Dynamic Weight
    ↓
Ensemble
    ↓
Prediction
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp
from math import factorial

from app.models import Fixture
from app.models import Prediction

from prediction.dynamic_weight import (
    DynamicWeightEngine,
    DynamicWeightInput,
)

from prediction.elo_engine import (
    EloEngine,
    EloTeam,
)

from prediction.ensemble_engine import (
    EnsembleDecisionEngine,
)

from prediction.explain import (
    PredictionExplanation,
)

from prediction.form_engine import (
    FormEngine,
    FormTeam,
)

from prediction.models import (
    EnginePrediction,
)

from prediction.xg_engine import (
    XGEngine,
    XGTeam,
)


@dataclass(frozen=True, slots=True)
class TeamForm:
    """
    Shared team information collected before kickoff.
    """

    scored: float

    conceded: float

    form_points: float

    samples: int

    elo: float = 1500.0

    expected_goals: float = 1.40

    expected_goals_against: float = 1.10

    shots_on_target: float = 5.0

    big_chances: float = 2.0

    conversion_rate: float = 0.35

    unbeaten_streak: int = 0

    wins_last_five: int = 2


class PredictionEngine:
    """
    Main prediction engine.

    Keeps the existing API while internally using
    multiple prediction engines.
    """

    def __init__(self) -> None:

        self.elo_engine = EloEngine()

        self.form_engine = FormEngine()

        self.xg_engine = XGEngine()

        self.weight_engine = DynamicWeightEngine()

        self.ensemble_engine = EnsembleDecisionEngine()

        self.explainer = PredictionExplanation()

    def predict(
        self,
        fixture: Fixture,
        home: TeamForm,
        away: TeamForm,
        confidence: float,
        lineup_verified: bool,
    ) -> Prediction:

        poisson_prediction = self._poisson_prediction(
            fixture,
            home,
            away,
        )

        elo_prediction = self.elo_engine.predict(
            EloTeam(
                fixture.home,
                home.elo,
            ),
            EloTeam(
                fixture.away,
                away.elo,
            ),
        )

        form_prediction = self.form_engine.predict(
            FormTeam(
                fixture.home,
                home.form_points,
                home.scored,
                home.conceded,
                home.unbeaten_streak,
                home.wins_last_five,
            ),
            FormTeam(
                fixture.away,
                away.form_points,
                away.scored,
                away.conceded,
                away.unbeaten_streak,
                away.wins_last_five,
            ),
        )

        xg_prediction = self.xg_engine.predict(
            XGTeam(
                fixture.home,
                home.expected_goals,
                home.expected_goals_against,
                home.shots_on_target,
                home.big_chances,
                home.conversion_rate,
            ),
            XGTeam(
                fixture.away,
                away.expected_goals,
                away.expected_goals_against,
                away.shots_on_target,
                away.big_chances,
                away.conversion_rate,
            ),
        )
                metrics = DynamicWeightInput(
            poisson_quality=min(
                1.0,
                (home.samples + away.samples) / 20,
            ),
            elo_quality=EloEngine.calibration_factor(
                home.elo - away.elo,
            ),
            form_quality=FormEngine.consistency_score(home=form_prediction and FormTeam(
                fixture.home,
                home.form_points,
                home.scored,
                home.conceded,
                home.unbeaten_streak,
                home.wins_last_five,
            )),
            xg_quality=XGEngine.quality_score(
                XGTeam(
                    fixture.home,
                    home.expected_goals,
                    home.expected_goals_against,
                    home.shots_on_target,
                    home.big_chances,
                    home.conversion_rate,
                ),
            ),
        )

        weights = self.weight_engine.calculate(
            metrics,
        )

        ensemble = self.ensemble_engine.combine(
            predictions=[
                poisson_prediction,
                elo_prediction,
                form_prediction,
                xg_prediction,
            ],
            weights=weights,
        )

        explanation = self.explainer.short_summary(
            ensemble,
        )

        if ensemble.winner == "HOME":
            winner = fixture.home

        elif ensemble.winner == "AWAY":
            winner = fixture.away

        else:
            winner = "Beraberlik"

        return Prediction(
            fixture_id=fixture.id,
            fixture=f"{fixture.home} - {fixture.away}",
            winner=winner,
            home_goals=ensemble.home_goals,
            away_goals=ensemble.away_goals,
            confidence=confidence,
            lineup_verified=lineup_verified,
            note=explanation,
        )

    def _poisson_prediction(
        self,
        fixture: Fixture,
        home: TeamForm,
        away: TeamForm,
    ) -> EnginePrediction:
        """
        Original Poisson engine.

        Preserved for backward compatibility.
        """

        home_lambda = max(
            0.2,
            min(
                3.5,
                (
                    (home.scored + away.conceded) / 2
                )
                + 0.18
                + (
                    home.form_points
                    - away.form_points
                )
                * 0.06,
            ),
        )

        away_lambda = max(
            0.2,
            min(
                3.5,
                (
                    (away.scored + home.conceded) / 2
                )
                - (
                    home.form_points
                    - away.form_points
                )
                * 0.06,
            ),
        )

        score, probability = max(
            (
                (
                    (h, a),
                    self._poisson(h, home_lambda)
                    * self._poisson(
                        a,
                        away_lambda,
                    ),
                )
                for h in range(6)
                for a in range(6)
            ),
            key=lambda item: item[1],
        )
                if score[0] > score[1]:
            winner = fixture.home

        elif score[1] > score[0]:
            winner = fixture.away

        else:
            winner = "Beraberlik"

        return EnginePrediction(
            engine="poisson",
            fixture_id=fixture.id,
            fixture_name=f"{fixture.home} - {fixture.away}",
            home_goals=score[0],
            away_goals=score[1],
            probability=round(
                probability,
                4,
            ),
            confidence=round(
                probability * 100,
                2,
            ),
            weight=1.0,
            explanation=(
                f"Poisson predicts "
                f"{winner} "
                f"({score[0]}-{score[1]})"
            ),
        )

    @staticmethod
    def _poisson(
        goals: int,
        rate: float,
    ) -> float:
        """
        Calculates a Poisson probability.
        """

        return (
            exp(-rate)
            * rate**goals
            / factorial(goals)
        )
