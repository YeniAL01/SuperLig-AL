"""
Ensemble Decision Engine

Sprint 1

Combines every prediction engine into one explainable prediction.

Current engines

- Poisson
- Elo
- Form
- xG

Future engines can easily be added without changing this class.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from prediction.models import (
    EnginePrediction,
    EnsembleResult,
    WeightProfile,
)


@dataclass(slots=True)
class EnsembleDecisionEngine:
    """
    Produces the final prediction from all engines.
    """

    def combine(
        self,
        predictions: list[EnginePrediction],
        weights: WeightProfile,
    ) -> EnsembleResult:

        score_votes: dict[
            tuple[int, int],
            float,
        ] = defaultdict(float)

        explanations: list[str] = []

        engine_scores: dict[str, float] = {}

        engine_weights = weights.as_dict()

        for prediction in predictions:

            weight = (
                engine_weights.get(
                    prediction.engine,
                    0.25,
                )
                * prediction.weight
            )

            vote = (
                prediction.probability
                * weight
            )

            score_votes[
                (
                    prediction.home_goals,
                    prediction.away_goals,
                )
            ] += vote

            explanations.append(
                prediction.explanation
            )

            engine_scores[
                prediction.engine
            ] = prediction.probability

        final_score = max(
            score_votes.items(),
            key=lambda item: item[1],
        )[0]

        probability = max(
            score_votes.values()
        )

        confidence = self._confidence(
            predictions,
            probability,
        )

        winner = self._winner(
            final_score,
        )

        return EnsembleResult(
            home_goals=final_score[0],
            away_goals=final_score[1],
            probability=round(
                probability,
                4,
            ),
            confidence=confidence,
            winner=winner,
            explanations=explanations,
            engine_scores=engine_scores,
            engine_weights=engine_weights,
        )

    @staticmethod
    def _winner(
        score: tuple[int, int],
    ) -> str:

        if score[0] > score[1]:
            return "HOME"

        if score[1] > score[0]:
            return "AWAY"

        return "DRAW"

    @staticmethod
    def _confidence(
        predictions: list[EnginePrediction],
        probability: float,
    ) -> float:
        """
        Temporary confidence.

        Sprint 2 will replace this with the new
        Confidence Engine.
        """

        if not predictions:
            return 0.0

        average = (
            sum(
                p.confidence
                for p in predictions
            )
            / len(predictions)
        )

        confidence = (
            average * 0.70
            + probability * 100 * 0.30
        )

        return round(
            min(
                confidence,
                95.0,
            ),
            1,
        )

    @staticmethod
    def agreement_ratio(
        predictions: list[EnginePrediction],
    ) -> float:
        """
        Returns model agreement between 0-1.
        """

        if not predictions:
            return 0.0

        winners = defaultdict(int)

        for prediction in predictions:

            if (
                prediction.home_goals
                > prediction.away_goals
            ):
                winners["HOME"] += 1

            elif (
                prediction.home_goals
                < prediction.away_goals
            ):
                winners["AWAY"] += 1

            else:
                winners["DRAW"] += 1

        majority = max(
            winners.values()
        )

        return round(
            majority
            / len(predictions),
            4,
        )
