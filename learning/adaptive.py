"""Regularized expert weights from immutable pre-match forecasts."""
from datetime import datetime
from math import exp, isfinite, log

LABELS = ("HOME", "DRAW", "AWAY")

def timestamp(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise ValueError("Timezone is required")
    return dt

def valid_probs(probs: object) -> bool:
    return (isinstance(probs, dict) and set(probs) == set(LABELS)
            and all(isinstance(v, (float, int)) and isfinite(v) and 0 < v < 1
                    for v in probs.values()) and abs(sum(probs.values())-1) < 1e-6)

def eligible(records: list, cutoff: datetime) -> list:
    selected, seen = [], set()
    for r in records:
        try:
            key = str(r["fixture_id"])
            if (key in seen or r.get("model_version") != "adaptive-v2" or
                    not timestamp(r["created_at"]) < timestamp(r["kickoff"]) <
                    timestamp(r["settled_at"]) <= cutoff):
                continue
            if r.get("actual_outcome") not in LABELS:
                continue
            selected.append(r)
            seen.add(key)
        except (KeyError, ValueError, TypeError):
            continue
    return sorted(selected, key=lambda r: timestamp(r["settled_at"]))[-300:]

def model_weights(records: list, names: list[str], cutoff: datetime) -> dict:
    rows = eligible(records, cutoff)
    scores = {}
    for name in names:
        loss, mass = 20 * log(3), 20.
        for age, row in enumerate(reversed(rows)):
            p = row.get("component_probabilities", {}).get(name)
            if valid_probs(p):
                weight = .99 ** age
                loss += -log(p[row["actual_outcome"]]) * weight
                mass += weight
        scores[name] = exp(-3 * loss / mass)
    total = sum(scores.values())
    return {name: .1/len(names) + .9*value/total for name, value in scores.items()}

