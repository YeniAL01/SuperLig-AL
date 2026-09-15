"""SuperLig-AL command-line entry point."""
from __future__ import annotations
import argparse
from config.settings import Settings
from collectors.fotmob import FotMobCollector
from app.service import PredictionService
from database.store import JsonStore
from learning.performance import score_prediction
from memory.engine import update_memory
from utils.logging import configure_logging

def learn(settings: Settings, collector: FotMobCollector) -> int:
    """Settle locked predictions for which FotMob exposes a final score."""
    logger, store = configure_logging(settings), JsonStore(settings.data_dir)
    predictions, records = store.read("predictions", []), store.read("performance", [])
    settled_ids = {int(r["fixture_id"]) for r in records}
    memory, added = store.read("memory", {}), 0
    for prediction in predictions:
        if int(prediction["fixture_id"]) in settled_ids:
            continue
        try:
            detail = collector.match(int(prediction["fixture_id"]))
            header = detail.get("header", {})
            status = header.get("status", {})
            teams = header.get("teams", [])
            actual = _final_score(teams)
            if not status.get("finished") or actual is None:
                continue
            actual_home, actual_away = actual
            result = {**prediction, **score_prediction(prediction, actual_home, actual_away), "actual_home": actual_home, "actual_away": actual_away}
            records.append(result)
            memory = update_memory(memory, result)
            added += 1
        except Exception as exc:
            logger.warning("learning_collection_failed fixture_id=%s error=%s", prediction["fixture_id"], exc)
    store.write("performance", records)
    store.write("memory", memory)
    logger.info("learning_completed settled=%s", added)
    return added

def _final_score(teams: object) -> tuple[int, int] | None:
    """Read either known FotMob home/away or two-row score representations."""
    if isinstance(teams, dict):
        home, away = teams.get("home", {}), teams.get("away", {})
        if isinstance(home, dict) and isinstance(away, dict) and home.get("score") is not None and away.get("score") is not None:
            return int(home["score"]), int(away["score"])
    if isinstance(teams, list) and len(teams) >= 2:
        if teams[0].get("score") is not None and teams[1].get("score") is not None:
            return int(teams[0]["score"]), int(teams[1]["score"])
    return None

def main() -> int:
    """Run prediction or learning task selected by the CLI."""
    parser = argparse.ArgumentParser(description="SuperLig-AL")
    parser.add_argument("command", choices=("predict", "learn"))
    args = parser.parse_args()
    settings = Settings()
    logger = configure_logging(settings)
    collector = FotMobCollector()
    if args.command == "predict":
        return PredictionService(settings, collector, logger).run()
    return learn(settings, collector)

if __name__ == "__main__":
    main()
