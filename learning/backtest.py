"""Walk-forward CSV evaluation; never writes to live model state."""
import csv
from datetime import timedelta
from math import log
from app.models import Fixture
from learning.adaptive import timestamp
from learning.history import forms, merge_results
from learning.performance import score_prediction, summarize
from prediction.engine import PredictionEngine

def read_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as stream:
        return merge_results([], list(csv.DictReader(stream)))

def evaluate(results, minimum_probability=58.0):
    history = merge_results([], results)
    records = []
    # Fixture IDs in CSV need not be numeric.
    for index, r in enumerate(history):
        start = timestamp(r["kickoff"])
        as_of = start-timedelta(minutes=15)
        home, away = forms(history, r["home_team"], r["away_team"], as_of)
        fx = Fixture(index+1, r["home_team"], r["away_team"], start)
        p = PredictionEngine(records).predict(fx, home, away, as_of=as_of)
        payload = p.payload()
        payload["fixture_id"] = r["fixture_id"]
        record = {**payload, **score_prediction(payload, r["home_goals"], r["away_goals"]),
                  "actual_home": r["home_goals"], "actual_away": r["away_goals"],
                  "settled_at": r["available_at"],
                  "publishable": p.confidence >= minimum_probability and p.data_quality >= .5}
        records.append(record)
    report = summarize(records)
    # Baseline evaluated on exactly the same targets.
    report["baseline"] = {
        "description": "Fixed HOME=.45 DRAW=.27 AWAY=.28; not fitted to this dataset",
        "accuracy": sum(r["actual_outcome"]=="HOME" for r in records)/len(records) if records else None,
        "log_loss": sum(-log({"HOME":.45,"DRAW":.27,"AWAY":.28}[r["actual_outcome"]])
                        for r in records)/len(records) if records else None}
    report["method"] = "Chronological T-15 walk-forward, only earlier available results; no tuning on test outcomes."
    report["records"] = records
    return report

