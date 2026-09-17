"""Regression tests for learning, time boundaries, persistence and workflows."""
from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import logging
import pytest
from app.models import Fixture
from app.service import PredictionService
from collectors.fotmob import FotMobCollector
from config.settings import Settings
from database.store import JsonStore
from learning.adaptive import model_weights
from learning.backtest import evaluate
from learning.history import forms, merge_results, validate_result
from learning.performance import score_prediction, summarize
from main import learn
from prediction.engine import PredictionEngine, TeamForm, score_grid, probabilities

START = datetime(2025,1,1,tzinfo=UTC)

def result(i, h=2, a=0, day=None):
    start = START+timedelta(days=i if day is None else day)
    return {"fixture_id": str(i), "home_team":"A", "away_team":"B",
            "home_goals":h, "away_goals":a, "kickoff":start.isoformat(),
            "available_at":(start+timedelta(hours=3)).isoformat()}

def forecast(i=1):
    now = START+timedelta(days=i)
    fx = Fixture(i,"A","B",now+timedelta(minutes=15))
    form = TeamForm(1.4,1.1,1.5,10)
    return PredictionEngine().predict(fx,form,form,99,True,as_of=now)

def test_probability_distribution_and_score():
    p = forecast()
    assert sum(p.probabilities.values()) == pytest.approx(1)
    assert sum(p.model_weights.values()) == pytest.approx(1)
    assert p.confidence == round(100*max(p.probabilities.values()),2)
    assert p.score_probability < p.confidence/100
    assert p.home_goals > p.away_goals if p.outcome=="HOME" else True
    assert "xg" not in p.component_probabilities
    assert sum(score_grid(4.5,4.5).values()) == pytest.approx(1)
    assert sum(probabilities(score_grid(4.5,4.5)).values()) == pytest.approx(1)

def test_kickoff_guard():
    fx=Fixture(1,"A","B",START)
    f=TeamForm(1,1,1,10)
    with pytest.raises(ValueError):
        PredictionEngine().predict(fx,f,f,as_of=START)

def test_form_perspective_and_no_future_leak():
    rows=[result(1,0,3),result(2,7,0)]
    h,a=forms(rows,"A","B",START+timedelta(days=2))
    assert h.samples == 1 and a.samples == 1
    assert h.scored == 0 and h.conceded == 3
    assert a.scored == 3 and a.conceded == 0
    assert h.elo < 1500 < a.elo

def test_weights_learn_and_ignore_duplicates_future_and_legacy():
    rows=[]
    for i in range(1,40):
        p=forecast(i).payload()
        p.update(actual_outcome="HOME", settled_at=(START+timedelta(days=i,hours=3)).isoformat())
        p["component_probabilities"]={
            "good":{"HOME":.8,"DRAW":.1,"AWAY":.1},
            "bad":{"HOME":.1,"DRAW":.1,"AWAY":.8}}
        rows.append(p)
    cutoff=START+timedelta(days=45)
    weights=model_weights(rows,["good","bad"],cutoff)
    assert weights["good"] > weights["bad"]
    assert model_weights(rows+rows,["good","bad"],cutoff) == weights
    assert model_weights(rows,["good","bad"],START) == {"good":.5,"bad":.5}
    legacy=[{**r,"model_version":"legacy"} for r in rows]
    assert model_weights(legacy,["good","bad"],cutoff) == {"good":.5,"bad":.5}

def test_backtest_future_changes_do_not_change_earlier_predictions():
    rows=[result(i,2 if i%2 else 0,1) for i in range(1,25)]
    before=evaluate(rows)
    rows[-1]["home_goals"]=9
    after=evaluate(rows)
    assert before["records"][:-1] == after["records"][:-1]
    assert before["records"][-1]["probabilities"] == after["records"][-1]["probabilities"]

def test_simultaneous_games_do_not_train_each_other():
    rows=[result(1,2,0,day=1),result(2,0,3,day=1)]
    records=evaluate(rows)["records"]
    assert records[0]["probabilities"] == records[1]["probabilities"]
    assert records[0]["model_weights"] == records[1]["model_weights"]

def test_results_validation_conflicts_and_idempotence():
    rows=merge_results([], [result(1)])
    assert merge_results(rows,rows) == rows
    with pytest.raises(ValueError):
        merge_results(rows,[result(1,4)])
    with pytest.raises(ValueError):
        validate_result({**result(1),"home_goals":-1})
    with pytest.raises(ValueError):
        validate_result({**result(1),"kickoff":"2025-01-01"})
    with pytest.raises(ValueError):
        validate_result({**result(1),"available_at":START.isoformat()})

def test_metrics_and_empty_state():
    p=forecast().payload()
    r={**p,**score_prediction(p,2,0),"publishable":True}
    summary=summarize([r])
    assert summary["coverage"] == 1
    assert summary["all"]["log_loss"] > 0
    assert summary["all"]["brier_score"] >= 0
    assert summarize([])["all"]["accuracy"] is None

def test_corruption_not_silently_reset(tmp_path):
    (tmp_path/"performance.json").write_text("{broken",encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        JsonStore(tmp_path).read("performance",[])

class OfflineCollector:
    def __init__(self, rows=None, fixtures=None):
        self.rows=rows or []
        self.upcoming=fixtures or []
    def results(self, league_id):
        return self.rows
    def fixtures(self, league_id):
        return self.upcoming
    def match(self, fixture_id):
        return {"header":{"status":{"finished":False}}}

def settings(tmp_path):
    return Settings(data_dir=tmp_path/"data",log_dir=tmp_path/"logs",report_dir=tmp_path/"reports",
                    prediction_token=None,prediction_chat_id=None)

def test_learning_retry_is_idempotent_and_preserves_prediction(tmp_path):
    cfg=settings(tmp_path)
    store=JsonStore(cfg.data_dir)
    p=forecast().payload()
    store.write("forecasts",[{**p,"publishable":False}])
    store.write("predictions",[p])
    collector=OfflineCollector([result(1)])
    assert learn(cfg,collector) == 1
    assert learn(cfg,collector) == 0
    assert len(store.read("performance",[])) == 1
    assert store.read("predictions",[]) == [p]
    assert store.read("memory",{})["A"]["matches"] == 1
    assert store.read("model_state",{})["settled_matches"] == 1

def test_low_data_forecast_is_locked_but_not_published(tmp_path):
    cfg=settings(tmp_path)
    fx=Fixture(123,"A","B",datetime.now(UTC)+timedelta(minutes=10))
    service=PredictionService(cfg,OfflineCollector(fixtures=[fx]),logging.getLogger("test"))
    assert service.run() == 0
    assert service.run() == 0
    assert len(service.store.read("forecasts",[])) == 1
    assert service.store.read("predictions",[]) == []

def test_provider_supported_shapes_and_unknown_schema():
    class Client:
        def __init__(self,data): self.data=data
        def get_json(self,*args): return self.data
    m={"id":1,"home":{"name":"A","score":2},"away":{"name":"B","score":1},
       "status":{"finished":True,"utcTime":START.isoformat()}}
    for key in ("fixtures","matches"):
        collector=FotMobCollector(Client({key:{"allMatches":[m]}}))
        assert collector.results(71)[0]["home_goals"] == 2
        assert collector.fixtures(71) == []
    with pytest.raises(ValueError):
        FotMobCollector(Client({})).results(71)


def test_observed_provider_score_string():
    class Client:
        def get_json(self,*args):
            return {"fixtures":{"allMatches":[
                {"id":"9","home":{"name":"A"},"away":{"name":"B"},
                 "status":{"finished":True,"utcTime":START.isoformat(),"scoreStr":"2 - 2"}},
                {"id":"10","home":{"name":"A"},"away":{"name":"B"},
                 "status":{"finished":True,"utcTime":START.isoformat(),"scoreStr":"P 4-3"}},
            ]}}
    rows=FotMobCollector(Client()).results(71)
    assert len(rows)==1 and rows[0]["home_goals"]==2 and rows[0]["away_goals"]==2

def test_legacy_engines_remain_callable():
    from prediction.elo_engine import EloEngine, EloTeam
    from prediction.form_engine import FormEngine, FormTeam
    from prediction.xg_engine import XGEngine, XGTeam
    from prediction.ensemble_engine import EnsembleDecisionEngine
    from prediction.models import WeightProfile
    p=EloEngine().predict(EloTeam("A",1500),EloTeam("B",1500))
    f=FormTeam("A",1.5,1.2,1.1,2,2)
    x=XGTeam("A",1.2,1.1,3,2,.3)
    items=[p,FormEngine().predict(f,f),XGEngine().predict(x,x)]
    combined=EnsembleDecisionEngine().combine(items,WeightProfile())
    assert combined.fixture_name == "A - B"

def test_cli_success_is_zero_for_nonzero_match_count(monkeypatch):
    import main
    monkeypatch.setattr("sys.argv",["main.py","predict"])
    monkeypatch.setattr(main,"configure_logging",lambda settings:logging.getLogger("test"))
    monkeypatch.setattr(main.PredictionService,"run",lambda self:3)
    assert main.main()==0

def test_missing_xg_never_synthesized():
    from dataclasses import replace
    now=START
    fx=Fixture(1,"A","B",START+timedelta(hours=1))
    f=TeamForm(1.2,1,1,10)
    g=replace(f,expected_goals=1.1,expected_goals_against=1.2)
    assert "xg" not in PredictionEngine().predict(fx,g,f,as_of=now).component_probabilities
    assert "xg" in PredictionEngine().predict(fx,g,g,as_of=now).component_probabilities

def test_lock_reconciliation_and_no_unconfigured_delivery(tmp_path,monkeypatch):
    cfg=settings(tmp_path)
    from dataclasses import replace
    p=replace(forecast(),kickoff=(datetime.now(UTC)+timedelta(minutes=10)).isoformat())
    store=JsonStore(cfg.data_dir)
    store.write("forecasts",[{**p.payload(),"publishable":True}])
    service=PredictionService(cfg,OfflineCollector(),logging.getLogger("test"))
    service.run()
    service.run()
    assert store.read("predictions",[]) == [p.payload()]
    assert store.read("delivery",{}) == {}

def test_legacy_winner_scoring_all_outcomes():
    p={"fixture":"A - B","winner":"B","home_goals":0,"away_goals":1}
    assert score_prediction(p,0,1)["winner_correct"]
    assert not score_prediction(p,2,1)["winner_correct"]
    p["winner"]="Beraberlik"
    assert score_prediction(p,0,0)["winner_correct"]

