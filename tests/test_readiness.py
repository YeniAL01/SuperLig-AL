"""Regression tests for October 2026 pre-activation safety fixes."""
from datetime import UTC, datetime, timedelta
import logging
from pathlib import Path
from types import SimpleNamespace

from app.models import Fixture
from app.service import PredictionService
from app.test_run import _build_future_predictions
from database.store import JsonStore


def _settings(path):
    return SimpleNamespace(
        data_dir=path,
        league_id=71,
        minimum_probability=58.0,
        prediction_token="",
        prediction_chat_id="",
    )


class Collector:
    def __init__(self, fixture, detail=None):
        self.fixture = fixture
        self.detail = detail or {"content": {"lineup": {}}}
        self.calls = 0

    def fixtures(self, _):
        return [self.fixture]

    def results(self, _):
        return []

    def match(self, _):
        self.calls += 1
        return self.detail


def test_projected_eleven_is_not_official_eleven():
    starters = [{"id": i} for i in range(11)]
    detail = {"content": {"lineup": {
        "lineupType": "predicted",
        "homeTeam": {"starters": starters},
        "awayTeam": {"starters": starters},
    }}}
    assert PredictionService._lineup_verified(detail) is False
    detail["content"]["lineup"]["lineupType"] = "standard"
    assert PredictionService._lineup_verified(detail) is True
    del detail["content"]["lineup"]["lineupType"]
    assert PredictionService._lineup_verified(detail) is False


def test_final_15_minute_fallback_when_cron_missed_earlier_runs(tmp_path):
    fixture = Fixture(3001, "Ev", "Dep", datetime.now(UTC) + timedelta(minutes=12))
    collector = Collector(fixture)
    service = PredictionService(_settings(tmp_path), collector, logging.getLogger("readiness"))
    assert service.run() == 1
    assert collector.calls == 1
    state = service.store.read("pre_match_analysis", {})[str(fixture.id)]
    assert state["lineup_attempts"] == 1
    assert state["lineup_verified"] is False
    assert state["lineup_fallback"] is True
    forecast, = service.store.read("forecasts", [])
    assert forecast["lineup_verified"] is False
    assert service.store.read("delivery", {})[str(fixture.id)]["status"] == "attempting"


def test_preview_uses_same_persisted_learning_state_as_live_engine(tmp_path, monkeypatch):
    fixture = Fixture(3002, "Ev", "Dep", datetime.now(UTC) + timedelta(hours=2))
    collector = Collector(fixture)
    state = {"version": 1, "markets": {"1x2": {"total_samples": 37}}}
    JsonStore(tmp_path).write("learning_state", state)
    observed = {}

    class FakeEngine:
        def __init__(self, records, learning_state):
            observed["learning_state"] = learning_state

        def predict(self, *args, **kwargs):
            return SimpleNamespace(fixture="Ev - Dep", winner="Ev", confidence=55.0, data_quality=0.0)

    monkeypatch.setattr("app.test_run.PredictionEngine", FakeEngine)
    result = _build_future_predictions(_settings(tmp_path), collector, logging.getLogger("readiness"))
    assert len(result) == 1
    assert observed["learning_state"] == state


def test_learning_workflow_shares_state_concurrency_group():
    root = Path(__file__).resolve().parents[1]
    for workflow in ("prediction", "learning", "weekly-report"):
        body = (root / ".github" / "workflows" / f"{workflow}.yml").read_text(encoding="utf-8")
        assert "group: superlig-state" in body


def test_learning_does_not_retrain_on_the_same_settled_matches():
    from learning.adaptive import update_learning_state

    now = datetime(2026, 10, 9, tzinfo=UTC)
    samples = [{
        "fixture_id": str(i),
        "market": "btts",
        "correct": False,
        "confidence": 80.0,
        "factors": {"goals": 0.8, "lineup": 1.0, "model_signal": 0.3},
        "settled_at": (now - timedelta(days=45-i)).isoformat(),
    } for i in range(30)]

    first, events1 = update_learning_state({}, samples, now=now)
    assert any(e["type"] == "critical_adaptation" for e in events1)
    first_market = first["markets"]["btts"]
    assert first_market["weights"]["goals"] < 1.0

    second, events2 = update_learning_state(first, samples, now=now+timedelta(days=1))
    second_market = second["markets"]["btts"]
    assert events2 == []
    assert second_market["weights"] == first_market["weights"]
    assert second_market["calibration_multiplier"] == first_market["calibration_multiplier"]
    assert second["audit"] == first["audit"]

    samples.append({
        "fixture_id": "30",
        "market": "btts",
        "correct": False,
        "confidence": 80.0,
        "factors": {"goals": 0.8, "lineup": 1.0, "model_signal": 0.3},
        "settled_at": (now - timedelta(days=15)).isoformat(),
    })
    third, events3 = update_learning_state(second, samples, now=now+timedelta(days=2))
    assert any(e["type"] == "critical_adaptation" for e in events3)
    assert third["markets"]["btts"]["weights"]["goals"] < second_market["weights"]["goals"]
