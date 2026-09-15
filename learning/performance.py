"""Result scoring and calibration tracking."""
from __future__ import annotations
from typing import Any

def score_prediction(prediction: dict[str, Any], home_goals: int, away_goals: int) -> dict[str, Any]:
    """Apply the project's 3+2 scoring rules to one prediction."""
    actual_winner = "Beraberlik" if home_goals == away_goals else prediction["fixture"].split(" - ")[0 if home_goals > away_goals else 1]
    winner_ok = prediction["winner"] == actual_winner
    score_ok = prediction["home_goals"] == home_goals and prediction["away_goals"] == away_goals
    return {"winner_correct": winner_ok, "score_correct": score_ok, "points": (3 if winner_ok else 0) + (2 if score_ok else 0)}

def calibration(records: list[dict[str, Any]]) -> float:
    """Return recent winner accuracy as a 0..1 calibration signal."""
    settled = [r for r in records if "winner_correct" in r]
    if not settled:
        return 0.5
    return sum(bool(r["winner_correct"]) for r in settled[-100:]) / len(settled[-100:])
