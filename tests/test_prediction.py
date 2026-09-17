"""Prediction unit tests."""
from datetime import UTC, datetime, timedelta
from app.models import Fixture
from prediction.confidence import ConfidenceEngine
from prediction.engine import PredictionEngine, TeamForm

def test_prediction_is_bounded() -> None:
    """The engine emits a valid score and confidence."""
    fixture = Fixture(1, "Ev", "Dep", datetime.now(UTC) + timedelta(hours=1))
    form = TeamForm(1.5, 1.0, 1.5, 10)
    prediction = PredictionEngine().predict(fixture, form, form, 70, True)
    assert 0 <= prediction.home_goals <= 5
    assert prediction.winner in {"Ev", "Dep", "Beraberlik"}

def test_unverified_lineup_is_penalized() -> None:
    """Confirmed lineup must improve confidence."""
    form = TeamForm(1.2, 1.2, 1.0, 10)
    engine = ConfidenceEngine()
    assert engine.calculate(form, form, True, .5) > engine.calculate(form, form, False, .5)
