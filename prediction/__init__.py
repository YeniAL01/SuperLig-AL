"""
Prediction package.

Sprint 1

Exports the complete prediction pipeline.

PredictionEngine
    ├── Poisson
    ├── Elo
    ├── Form
    ├── xG
    ├── Dynamic Weight
    ├── Ensemble
    └── Explain
"""

from prediction.engine import PredictionEngine
from prediction.engine import TeamForm

from prediction.confidence import ConfidenceEngine

from prediction.elo_engine import EloEngine
from prediction.elo_engine import EloTeam

from prediction.form_engine import FormEngine
from prediction.form_engine import FormTeam

from prediction.xg_engine import XGEngine
from prediction.xg_engine import XGTeam

from prediction.dynamic_weight import (
    DynamicWeightEngine,
    DynamicWeightInput,
)

from prediction.ensemble_engine import (
    EnsembleDecisionEngine,
)

from prediction.explain import (
    PredictionExplanation,
)

from prediction.models import (
    EnginePrediction,
    EnsembleResult,
    TeamStrength,
    WeightProfile,
)

__all__ = [
    # Main API
    "PredictionEngine",
    "ConfidenceEngine",
    "TeamForm",

    # Engines
    "EloEngine",
    "FormEngine",
    "XGEngine",
    "DynamicWeightEngine",
    "EnsembleDecisionEngine",
    "PredictionExplanation",

    # Inputs
    "EloTeam",
    "FormTeam",
    "XGTeam",
    "DynamicWeightInput",

    # Shared Models
    "EnginePrediction",
    "EnsembleResult",
    "TeamStrength",
    "WeightProfile",
]
