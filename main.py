"""SuperLig-AL CLI. Successful jobs always exit zero, regardless of match count."""
import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from config.settings import Settings
from collectors.fotmob import FotMobCollector
from app.service import PredictionService
from database.store import JsonStore
from learning.performance import score_prediction, summarize
from learning.history import merge_results
from learning.adaptive import model_weights
from memory.engine import update_memory
from utils.logging import configure_logging

def learn(settings, collector):
    logger, store = configure_logging(settings), JsonStore(settings.data_dir)
    conflicts = store.read("result_conflicts", [])
    results = merge_results(store.read("results", []), collector.results(settings.league_id), conflicts)
    store.write("results", results)
    store.write("result_conflicts", conflicts)
    by_id = {str(r["fixture_id"]): r for r in results}
    forecasts = store.read("forecasts", [])
    delivery = store.read("delivery", {})
    records = store.read("performance", [])
    settled = {str(r["fixture_id"]) for r in records}
    added = 0
    for p in forecasts:
        key = str(p["fixture_id"])
        if key in settled:
            continue
        actual = by_id.get(key)
        if actual and p.get("home_team") and (
                actual["home_team"] != p["home_team"] or actual["away_team"] != p["away_team"]):
            logger.warning("settlement_skipped fixture_id=%s reason=team_mismatch", key)
            continue
        if actual is None:
            try:
                detail = collector.match(int(key))
                header = detail.get("header", {})
                score = _final_score(header.get("teams", []))
                if not header.get("status", {}).get("finished") or score is None:
                    continue
                actual = {"home_goals": score[0], "away_goals": score[1],
                          "available_at": datetime.now(UTC).isoformat()}
            except Exception as exc:
                logger.warning("settlement_failed fixture_id=%s error=%s", key, type(exc).__name__)
                continue
        delivery_state = delivery.get(key)
        delivered = isinstance(delivery_state, str) or (
            isinstance(delivery_state, dict) and delivery_state.get("status") == "delivered")
        records.append({**p, **score_prediction(p, actual["home_goals"], actual["away_goals"]),
                        "eligible": bool(p.get("publishable")), "delivered": delivered,
                        "actual_home": actual["home_goals"], "actual_away": actual["away_goals"],
                        "settled_at": actual["available_at"]})
        settled.add(key)
        added += 1
    store.write("performance", records)
    # Derived files are rebuilt so a retry after a partial write is safe.
    memory = {}
    for row in records:
        memory = update_memory(memory, row)
    store.write("memory", memory)
    store.write("metrics", summarize(records))
    store.write("model_state", {"version": "adaptive-v2", "settled_matches": len(records),
                               "weights": model_weights(records, ["poisson","elo","baseline"], datetime.now(UTC))})
    logger.info("learning_completed settled=%s", added)
    return added

def _final_score(teams):
    if isinstance(teams, dict):
        teams = [teams.get("home", {}), teams.get("away", {})]
    if isinstance(teams, list) and len(teams) == 2 and all(
            isinstance(t, dict) and t.get("score") is not None for t in teams):
        scores = tuple(int(t["score"]) for t in teams)
        return scores if min(scores) >= 0 else None
    return None

def main():
    parser = argparse.ArgumentParser(description="SuperLig-AL")
    parser.add_argument("command", choices=("predict","deliver","learn","test","test-telegram","backtest","import-history","metrics"))
    parser.add_argument("--csv", type=Path)
    parser.add_argument("--output", type=Path, default=Path("reports/backtest.json"))
    args = parser.parse_args()
    settings = Settings()
    if args.command == "test-telegram":
        from telegram.client import TelegramClient
        logger = configure_logging(settings)
        client = TelegramClient(settings.prediction_token, settings.prediction_chat_id)
        logger.info("telegram_test_started token_set=%s chat_id_set=%s", bool(client.token), bool(client.chat_id))
        sent = client.send_text("✅ SuperLig-AL Telegram bağlantı testi başarılı.\n"
                                "Bu bir bağlantı testidir; maç tahmini değildir.")
        if sent:
            logger.info("telegram_test_success: Test mesajı Telegram API tarafından kabul edildi.")
            return 0
        logger.error("telegram_test_failed: Bot token/chat ID, botla sohbet ve kanal izinlerini kontrol edin.")
        return 1
    store = JsonStore(settings.data_dir)
    if args.command in ("backtest", "import-history"):
        if not args.csv:
            parser.error("--csv is required")
        from learning.backtest import read_csv, evaluate
        rows = read_csv(args.csv)
        if args.command == "import-history":
            conflicts = store.read("result_conflicts", [])
            merged = merge_results(store.read("results", []), rows, conflicts)
            store.write("results", merged)
            store.write("result_conflicts", conflicts)
            print(f"Historical matches: {len(merged)}")
        else:
            report = evaluate(rows, settings.minimum_probability)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps({k:v for k,v in report.items() if k != "records"}, ensure_ascii=False, indent=2))
        return 0
    if args.command == "metrics":
        print(json.dumps(summarize(store.read("performance", [])), ensure_ascii=False, indent=2))
        return 0
    logger, collector = configure_logging(settings), FotMobCollector()
    if args.command == "predict":
        PredictionService(settings, collector, logger).run()
    elif args.command == "deliver":
        return PredictionService(settings, collector, logger).deliver()
    elif args.command == "learn":
        learn(settings, collector)
    else:
        from app.test_run import run_test
        run_test(settings, collector, logger)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

