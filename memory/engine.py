"""Stores compact, evidence-based learning notes."""
from typing import Any

def update_memory(memory: dict[str, Any], record: dict[str, Any]) -> dict[str, Any]:
    """Update per-team aggregate outcomes after a settled fixture."""
    for team in record["fixture"].split(" - "):
        entry = memory.setdefault(team, {"matches": 0, "winner_hits": 0})
        entry["matches"] += 1
        entry["winner_hits"] += int(record["winner_correct"])
    return memory
