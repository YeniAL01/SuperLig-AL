"""Weekly report task entry point."""
from datetime import datetime
from config.settings import Settings
from database.store import JsonStore
from reporting.png_report import create_weekly_report
from telegram.client import TelegramClient
from utils.logging import configure_logging

def main() -> None:
    """Create and deliver one report from all settled local records."""
    settings = Settings()
    logger = configure_logging(settings)
    records = JsonStore(settings.data_dir).read("performance", [])
    stamp = datetime.now().strftime("%Y-%m-%d")
    path = create_weekly_report(records, settings.report_dir / f"weekly-{stamp}.png")
    sent = TelegramClient(settings.report_token, settings.report_chat_id).send_photo(path, "SuperLig-AL haftalık raporu")
    logger.info("weekly_report_generated path=%s telegram_sent=%s", path, sent)

if __name__ == "__main__":
    main()
