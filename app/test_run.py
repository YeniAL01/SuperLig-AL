"""Manual end-to-end test: next-week predictions + synthetic performance."""
from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
import logging

from app.models import Fixture, Prediction
from collectors.fotmob import FotMobCollector
from config.settings import Settings
from learning.performance import score_prediction
from prediction.confidence import ConfidenceEngine
from prediction.engine import PredictionEngine, TeamForm
from telegram.client import TelegramClient


def run_test(settings: Settings, collector: FotMobCollector, logger: logging.Logger) -> int:
    """
    Manually simulate the full pipeline for upcoming fixtures (next 8 days).

    - Builds real model predictions (no T-15 / threshold gate).
    - Sends each prediction to Telegram with a [TEST] prefix.
    - Draws random 'actual' scores only for the test.
    - Scores AL performance and sends a summary.
    - Does NOT write to production predictions / performance / memory stores.
    - Always returns 0 on completion so CI does not treat match-count as exit code.
    """
    token = (settings.prediction_token or "").strip() or None
    chat_id = (settings.prediction_chat_id or "").strip() or None
    telegram = TelegramClient(token, chat_id)
    engine = PredictionEngine()
    confidence_engine = ConfidenceEngine()

    logger.info(
        "telegram_status enabled=%s token_set=%s chat_id_set=%s chat_id_len=%s",
        telegram.enabled,
        bool(token),
        bool(chat_id),
        len(chat_id or ""),
    )

    now = datetime.now(UTC)
    horizon = now + timedelta(days=8)
    fixtures = [
        fx
        for fx in collector.fixtures(settings.league_id)
        if now < fx.start <= horizon
    ]
    fixtures.sort(key=lambda f: f.start)

    if not fixtures:
        msg = "[TEST] Önümüzdeki 8 günde Super Lig maçı bulunamadı."
        logger.info(msg)
        ok = telegram.send_text(msg)
        logger.info("telegram_send_empty ok=%s", ok)
        return 0

    header = (
        f"[TEST] SuperLig-AL deneme çalışması\n"
        f"Maç sayısı: {len(fixtures)}\n"
        f"Pencere: {now.date()} → {horizon.date()}\n"
        f"Not: Skorlar rastgele simüle edilir; üretim verisine yazılmaz."
    )
    logger.info("test_run_started fixtures=%s", len(fixtures))
    ok_header = telegram.send_text(header)
    logger.info("telegram_send_header ok=%s", ok_header)

    records: list[dict] = []
    sent_ok = 0
    for fixture in fixtures:
        prediction = _predict_fixture(collector, engine, confidence_engine, fixture, logger)
        if _send_prediction(telegram, prediction):
            sent_ok += 1
        actual_home, actual_away = _random_score()
        payload = prediction.payload()
        scored = score_prediction(payload, actual_home, actual_away)
        record = {
            **payload,
            **scored,
            "actual_home": actual_home,
            "actual_away": actual_away,
            "kickoff": fixture.start.isoformat(),
        }
        records.append(record)
        logger.info(
            "test_fixture fixture_id=%s pred=%s-%s actual=%s-%s points=%s",
            fixture.id,
            prediction.home_goals,
            prediction.away_goals,
            actual_home,
            actual_away,
            scored["points"],
        )

    summary = _build_summary(records)
    logger.info("test_run_summary %s", summary.replace("\n", " | "))
    ok_summary = telegram.send_text(summary)
    logger.info(
        "telegram_send_summary ok=%s predictions_sent=%s/%s",
        ok_summary,
        sent_ok,
        len(fixtures),
    )
    if not telegram.enabled:
        logger.warning(
            "telegram_not_configured: Secrets TELEGRAM_PREDICTION_BOT_TOKEN / "
            "TELEGRAM_PREDICTION_CHAT_ID eksik veya boş."
        )
    elif sent_ok == 0 and not ok_header:
        logger.warning(
            "telegram_all_sends_failed: Bot token/chat_id hatalı olabilir, "
            "bot ile sohbet başlatılmamış olabilir veya chat_id yanlış olabilir."
        )
    return 0


def _predict_fixture(
    collector: FotMobCollector,
    engine: PredictionEngine,
    confidence_engine: ConfidenceEngine,
    fixture: Fixture,
    logger: logging.Logger,
) -> Prediction:
    """Build a model prediction; fall back to defaults if match detail fails."""
    home = TeamForm(1.0, 1.2, 1.0, 0)
    away = TeamForm(1.0, 1.2, 1.0, 0)
    lineup_verified = False
    try:
        detail = collector.match(fixture.id)
        lineup_verified = _lineup_verified(detail)
        home, away = _forms(detail)
    except Exception as exc:
        logger.warning("test_match_detail_failed fixture_id=%s error=%s", fixture.id, exc)

    confidence = confidence_engine.calculate(home, away, lineup_verified, calibration=0.5)
    # Test mode: always produce a forecast (no publication threshold).
    confidence = max(confidence, 55.0)
    prediction = engine.predict(fixture, home, away, confidence, lineup_verified)
    note = "TEST — üretim kilidi / eşiği uygulanmadı."
    if not lineup_verified:
        note += " İlk 11 doğrulanamadı; varsayılan form kullanıldı."
    return Prediction(
        prediction.fixture_id,
        prediction.fixture,
        prediction.winner,
        prediction.home_goals,
        prediction.away_goals,
        prediction.confidence,
        prediction.lineup_verified,
        note,
    )


def _send_prediction(telegram: TelegramClient, prediction: Prediction) -> bool:
    """Same body as production, with an explicit [TEST] prefix."""
    note = f"\nNot: {prediction.note}" if prediction.note else ""
    text = (
        f"[TEST]\n"
        f"⚽ {prediction.fixture}\n"
        f"Kazanan: {prediction.winner}\n"
        f"Tahmini skor: {prediction.home_goals}-{prediction.away_goals}\n"
        f"Güven: %{prediction.confidence:.1f}{note}"
    )
    return telegram.send_text(text)


def _random_score() -> tuple[int, int]:
    """Synthetic final score for performance dry-run only (0–3 goals each)."""
    return random.randint(0, 3), random.randint(0, 3)


def _build_summary(records: list[dict]) -> str:
    total = len(records)
    winners = sum(1 for r in records if r.get("winner_correct"))
    scores = sum(1 for r in records if r.get("score_correct"))
    points = sum(int(r.get("points", 0)) for r in records)
    accuracy = (winners / total * 100) if total else 0.0
    lines = [
        "[TEST] AL performans özeti (simüle skorlar)",
        f"Maç: {total}",
        f"Doğru kazanan: {winners}/{total} (%{accuracy:.1f})",
        f"Doğru skor: {scores}/{total}",
        f"Toplam puan: {points}  (kazanan +3, skor +2)",
        "",
        "Detay:",
    ]
    for r in records:
        lines.append(
            f"• {r.get('fixture')} | tah {r.get('home_goals')}-{r.get('away_goals')} "
            f"| sim {r.get('actual_home')}-{r.get('actual_away')} "
            f"| K{'✓' if r.get('winner_correct') else '✗'} "
            f"S{'✓' if r.get('score_correct') else '✗'} "
            f"| {r.get('points', 0)}p"
        )
    lines.append("")
    lines.append("Not: Gerçek sonuç değil; sadece mesaj formatı ve puanlama akışı testi.")
    return "\n".join(lines)


def _lineup_verified(detail: dict) -> bool:
    lineups = detail.get("content", {}).get("lineup", {})
    return bool(
        lineups.get("homeTeam", {}).get("starters")
        and lineups.get("awayTeam", {}).get("starters")
    )


def _forms(detail: dict) -> tuple[TeamForm, TeamForm]:
    form = detail.get("content", {}).get("form", {})

    def build(side: str) -> TeamForm:
        rows = form.get(side, []) if isinstance(form, dict) else []
        scores = [row.get("score", {}) for row in rows if isinstance(row, dict)]
        scored = sum(float(x.get("home", 0)) + float(x.get("away", 0)) for x in scores) / max(
            1, len(scores) * 2
        )
        return TeamForm(scored or 1.0, 1.2, 1.0, len(scores))

    return build("homeTeam"), build("awayTeam")
