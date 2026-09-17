"""Read-only preview. No Telegram delivery, random results, or live-state writes."""
from datetime import UTC, datetime, timedelta
from learning.history import forms, merge_results
from prediction.engine import PredictionEngine
from database.store import JsonStore

def run_test(settings, collector, logger):
    store = JsonStore(settings.data_dir)
    history = merge_results(store.read("results", []), collector.results(settings.league_id))
    records = store.read("performance", [])
    now = datetime.now(UTC)
    count = 0
    for fixture in sorted(collector.fixtures(settings.league_id), key=lambda f:f.start):
        if not now < fixture.start <= now+timedelta(days=8):
            continue
        home, away = forms(history, fixture.home, fixture.away, now)
        prediction = PredictionEngine(records).predict(fixture, home, away, as_of=now)
        logger.info("PREVIEW fixture=%s outcome=%s probability=%.2f quality=%.2f",
                    prediction.fixture, prediction.winner, prediction.confidence, prediction.data_quality)
        count += 1
    logger.info("preview_completed matches=%s; no delivery or performance claims", count)
    return 0

