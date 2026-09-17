"""
Dynamic Weight Engine

Sprint 1

This module dynamically adjusts the contribution of each prediction
engine before the Ensemble Decision Engine combines them.

The purpose is to avoid giving equal importance to every model when
their data quality or historical reliability differs.
"""

from __future__ import annotations

from dataclasses import dataclass

from prediction.models import WeightProfile


@dataclass(slots=True)
class DynamicWeightInput:
    """
    Inputs used to calculate dynamic engine weights.
    """

    poisson_quality: float
    elo_quality: float
    form_quality: float
    xg_quality: float

    poisson_accuracy: float = 0.50
    elo_accuracy: float = 0.50
    form_accuracy: float = 0.50
    xg_accuracy: float = 0.50


class DynamicWeightEngine:
    """
    Calculates normalized weights for every prediction engine.

    The result is consumed by EnsembleDecisionEngine.
    """

    MIN_WEIGHT = 0.10
    MAX_WEIGHT = 0.60

    def calculate(
        self,
        metrics: DynamicWeightInput,
    ) -> WeightProfile:
        """
        Calculate normalized engine weights.
        """

        poisson = self._combine(
            metrics.poisson_quality,
            metrics.poisson_accuracy,
        )

        elo = self._combine(
            metrics.elo_quality,
            metrics.elo_accuracy,
        )

        form = self._combine(
            metrics.form_quality,
            metrics.form_accuracy,
        )

        xg = self._combine(
            metrics.xg_quality,
            metrics.xg_accuracy,
        )

        profile = WeightProfile(
            poisson=poisson,
            elo=elo,
            form=form,
            xg=xg,
        )

        return profile.normalize()

    def _combine(
        self,
        quality: float,
        accuracy: float,
    ) -> float:
        """
        Merge quality and historical accuracy.
        """

        value = (
            quality * 0.60
            + accuracy * 0.40
        )

        value = max(
            self.MIN_WEIGHT,
            min(
                self.MAX_WEIGHT,
                value,
            ),
        )

        return round(value, 4)

    @staticmethod
    def agreement_bonus(
        agreement: float,
    ) -> float:
        """
        Bonus applied when engines agree.

        agreement:
            0.0 - 1.0
        """

        return round(
            agreement * 0.10,
            4,
        )

    @staticmethod
    def disagreement_penalty(
        disagreement: float,
    ) -> float:
        """
        Penalty applied when engines disagree.

        disagreement:
            0.0 - 1.0
        """

        return round(
            disagreement * 0.10,
            4,
        )

    @staticmethod
    def update_weight(
        current: float,
        success: bool,
        learning_rate: float = 0.05,
    ) -> float:
        """
        Online learning helper.

        Sprint 6 will call this method after every match.
        """

        if success:
            current += learning_rate
        else:
            current -= learning_rate

        return round(
            max(
                0.10,
                min(
                    0.70,
                    current,
                ),
            ),
            4,
        )
