"""Generate and deliver weekly + season AI performance reports."""
from datetime import UTC, datetime, timedelta
from config.settings import Settings
from collectors.fotmob import FotMobCollector
from database.store import JsonStore
from learning.adaptive import timestamp
from reporting.png_report import create_weekly_report, create_season_report
from telegram.client import TelegramClient
from utils.logging import configure_logging


def main()->int:
    settings=Settings(); settings.ensure_directories(); logger=configure_logging(settings); store=JsonStore(settings.data_dir)
    records=store.read('performance',[]); now=datetime.now(UTC)

    # Haftalık rapor yalnızca FotMob'un tamamen bitmiş olarak doğruladığı
    # en son Süper Lig haftasını değerlendirir.
    try:
        completed_round=FotMobCollector().latest_completed_round(settings.league_id)
    except Exception as exc:
        logger.warning('weekly_report_skipped reason=round_lookup_failed error=%s',exc)
        return 0
    if not completed_round:
        logger.info('weekly_report_skipped reason=no_completed_round')
        return 0

    fixture_ids=set(completed_round['fixture_ids'])
    weekly=[r for r in records if str(r.get('fixture_id','')) in fixture_ids and r.get('settled_at')]
    if not weekly:
        logger.info('weekly_report_skipped reason=no_predictions_for_completed_round round=%s',completed_round['round'])
        return 0

    # Son maçın sonucu sisteme yerleştikten tam 1 saat sonra rapor uygun olur.
    latest_settled=max(timestamp(r['settled_at']) for r in weekly)
    if now < latest_settled + timedelta(hours=1):
        logger.info('weekly_report_skipped reason=waiting_one_hour round=%s',completed_round['round'])
        return 0

    report_state=store.read('report_state',{})
    report_key=f"round:{completed_round['round']}"
    if report_state.get('last_weekly_key')==report_key:
        logger.info('weekly_report_skipped reason=already_sent round=%s',completed_round['round'])
        return 0

    stamp=now.strftime('%Y-%m-%d')
    weekly_path=create_weekly_report(weekly,settings.report_dir/f'weekly-{stamp}.png')
    season_path=create_season_report(records,settings.report_dir/f'season-{stamp}.png')
    client=TelegramClient(settings.report_token,settings.report_chat_id)
    if not client.enabled:return 1
    ok1=client.send_photo(weekly_path,f"Süper Lig • {completed_round['round']}. Hafta • Haftalık AL Performansı")
    ok2=client.send_photo(season_path,'Süper Lig • Sezon Geneli AL Performansı')
    if ok1 and ok2:
        report_state['last_weekly_key']=report_key
        report_state['last_round']=completed_round['round']
        report_state['sent_at']=now.isoformat()
        store.write('report_state',report_state)
        return 0
    return 1

if __name__=='__main__':raise SystemExit(main())
