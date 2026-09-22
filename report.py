"""Süper Lig AI performance report entry point."""
import os
from datetime import UTC, datetime, timedelta
from config.settings import Settings
from database.store import JsonStore
from collectors.fotmob import FotMobCollector
from learning.adaptive import timestamp
from learning.performance import score_prediction
from reporting.png_report import create_combined_report
from telegram.client import TelegramClient
from utils.logging import configure_logging

REPORT_PERIOD_DAYS=7

def main()->int:
    settings=Settings(); settings.ensure_directories(); logger=configure_logging(settings); store=JsonStore(settings.data_dir)
    records=store.read('performance',[]); now=datetime.now(UTC)
    # Backfill the new 40-point rubric in memory for historical real forecasts.
    enriched=[]
    for row in records:
        if all(k in row for k in ('winner_correct','ou25_correct','btts_correct','score_correct','points')):
            enriched.append(row); continue
        if row.get('actual_home') is None or row.get('actual_away') is None:
            enriched.append(row); continue
        enriched.append({**row, **score_prediction(row, int(row['actual_home']), int(row['actual_away']))})
    records=enriched
    round_info=FotMobCollector().latest_completed_round(settings.league_id)
    if not round_info:
        logger.info('weekly_report_skipped reason=no_fully_completed_round'); return 0
    if now < round_info['last_kickoff'] + timedelta(hours=1):
        logger.info('weekly_report_skipped reason=waiting_one_hour_after_last_match'); return 0
    fixture_ids=set(round_info['fixture_ids'])
    weekly=[r for r in records if str(r.get('fixture_id')) in fixture_ids]
    if not weekly:
        logger.info('weekly_report_skipped reason=no_performance_records_for_round'); return 0
    state=store.read('report_state',{})
    week_key=str(round_info['round'])
    force_resend=os.getenv('FORCE_RESEND','').strip().lower() in {'1','true','yes','on'}
    if state.get('last_round')==week_key and not force_resend:
        logger.info('weekly_report_skipped reason=already_sent round=%s',week_key); return 0
    if force_resend:
        logger.info('weekly_report_force_resend round=%s state_will_not_change=true',week_key)
    report_path=create_combined_report(
        weekly,
        records,
        settings.report_dir/f'al-performance-round-{week_key}.png',
        week_label=f'HAFTA {week_key}',
    )
    client=TelegramClient(settings.report_token,settings.report_chat_id)
    if not client.enabled: logger.error('weekly_report_delivery_failed reason=missing_telegram_credentials'); return 1
    if not client.send_photo(report_path,'Süper Lig | AL Performans Raporu'): return 1
    if not force_resend:
        store.write('report_state',{'last_round':week_key,'sent_at':now.isoformat()})
    logger.info('weekly_report_completed round=%s records=%s season=%s force_resend=%s',week_key,len(weekly),len(records),force_resend); return 0

if __name__=='__main__': raise SystemExit(main())
