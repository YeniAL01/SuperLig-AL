"""Proper probability metrics, accuracy, coverage, and reliability bins."""
from math import log, sqrt
from learning.adaptive import valid_probs, LABELS


def score_prediction(prediction: dict, home_goals: int, away_goals: int) -> dict:
    label = "HOME" if home_goals > away_goals else "AWAY" if away_goals > home_goals else "DRAW"
    teams = prediction["fixture"].split(" - ")
    actual_winner = {"DRAW": "Beraberlik", "HOME": prediction.get("home_team") or teams[0],
                     "AWAY": prediction.get("away_team") or teams[-1]}[label]
    winner_ok = (prediction.get("outcome") == label if prediction.get("outcome")
                 else prediction["winner"] == actual_winner)
    score_ok = prediction["home_goals"] == home_goals and prediction["away_goals"] == away_goals
    result = {"actual_outcome": label, "winner_correct": winner_ok, "score_correct": score_ok,
              "points": 3*int(winner_ok)+2*int(score_ok)}
    p = prediction.get("probabilities")
    if valid_probs(p):
        result["log_loss"] = -log(p[label])
        result["brier_score"] = sum((p[k]-int(k==label))**2 for k in LABELS)
    return result


def calibration(records: list) -> float:
    rows = [r for r in records if "winner_correct" in r][-100:]
    return sum(bool(r["winner_correct"]) for r in rows)/len(rows) if rows else .5


def summarize(records: list) -> dict:
    def group(rows):
        n = len(rows)
        hits = sum(bool(r["winner_correct"]) for r in rows)
        p = hits/n if n else 0
        z = 1.96
        denom = 1+z*z/n if n else 1
        center = (p+z*z/(2*n))/denom if n else 0
        half = z*sqrt(p*(1-p)/n+z*z/(4*n*n))/denom if n else 0
        scored = [r for r in rows if "log_loss" in r]
        return {"matches": n, "accuracy": p if n else None,
                "accuracy_95pct_interval": [max(0,center-half),min(1,center+half)] if n else None,
                "exact_score_accuracy": sum(r["score_correct"] for r in rows)/n if n else None,
                "log_loss": sum(r["log_loss"] for r in scored)/len(scored) if scored else None,
                "brier_score": sum(r["brier_score"] for r in scored)/len(scored) if scored else None}

    eligible = [r for r in records if r.get("eligible", r.get("publishable", False))]
    delivered = [r for r in records if r.get("delivered", False)]
    bins = []
    for low, high in ((0,40),(40,50),(50,60),(60,70),(70,80),(80,90),(90,101)):
        rows = [r for r in records if low <= r["confidence"] < high]
        if rows:
            bins.append({"range": [low, min(high,100)], "matches": len(rows),
                         "predicted": sum(r["confidence"] for r in rows)/len(rows)/100,
                         "observed": sum(r["winner_correct"] for r in rows)/len(rows)})
    total = len(records)
    return {
        "all": group(records),
        "eligible": group(eligible),
        "delivered": group(delivered),
        # Backward-compatible alias. It now explicitly means eligible, not delivered.
        "published": group(eligible),
        "eligible_coverage": len(eligible)/total if total else None,
        "delivery_coverage": len(delivered)/total if total else None,
        "coverage": len(eligible)/total if total else None,
        "reliability": bins,
    }
