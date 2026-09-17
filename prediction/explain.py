"""
Prediction explanation engine.

Sprint 1

Creates explainable AI summaries for every prediction.

The generated explanation is human readable and can be sent
directly to Telegram or stored for later reporting.
"""

from __future__ import annotations

from dataclasses import dataclass

from prediction.models import EnsembleResult


@dataclass(slots=True)
class PredictionExplanation:
    """
    Generates explainable prediction summaries.
    """

    def build(
        self,
        result: EnsembleResult,
    ) -> str:
        """
        Build a detailed explanation text.
        """

        lines: list[str] = []

        lines.append(
            f"Final Score Prediction: "
            f"{result.home_goals}-{result.away_goals}"
        )

        lines.append(
            f"Winner: {result.winner}"
        )

        lines.append(
            f"Confidence: {result.confidence:.1f}%"
        )

        lines.append("")

        lines.append("Engine Weights")

        for engine, weight in sorted(
            result.engine_weights.items()
        ):
            lines.append(
                f" • {engine}: {weight:.2f}"
            )

        lines.append("")

        lines.append("Engine Probabilities")

        for engine, probability in sorted(
            result.engine_scores.items()
        ):
            lines.append(
                f" • {engine}: {probability:.2%}"
            )

        if result.explanations:

            lines.append("")
            lines.append("Reasons")

            for reason in result.explanations:
                lines.append(f" • {reason}")

        return "\n".join(lines)

    @staticmethod
    def short_summary(
        result: EnsembleResult,
    ) -> str:
        """
        Short explanation for Telegram messages.
        """

        return (
            f"Tahmin: "
            f"{result.home_goals}-{result.away_goals} | "
            f"Güven %{result.confidence:.1f}"
        )

    @staticmethod
    def winner_reason(
        result: EnsembleResult,
    ) -> str:
        """
        Returns only the winner reason.
        """

        if not result.explanations:
            return "No explanation available."

        return result.explanations[0]
