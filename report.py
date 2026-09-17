"""Weekly Süper Lig performance report entry point."""

from datetime import UTC, datetime, timedelta

from config.settings import Settings
from database.store import JsonStore
from learning.adaptive import timestamp
from reporting.png_report import create_weekly_report
from telegram.client import TelegramClient
from utils.logging import configure_logging


REPORT_PERIOD_DAYS = 7


def main() -> int:
    """Create and deliver the weekly report.

    The report uses only settled records from the previous seven days.
    Telegram delivery failure returns a non-zero exit code so GitHub
    Actions cannot incorrectly report a successful delivery.
    """
    settings = Settings()
    settings.ensure_directories()

    logger = configure_logging(
        settings
    )

    store = JsonStore(
        settings.data_dir
    )

    records = store.read(
        "performance",
        [],
    )

    now = datetime.now(
        UTC
    )

    since = now - timedelta(
        days=REPORT_PERIOD_DAYS
    )

    weekly_records = [
        record
        for record in records
        if (
            record.get(
                "settled_at"
            )
            and timestamp(
                record["settled_at"]
            )
            >= since
        )
    ]

    eligible = sum(
        bool(
            record.get(
                "eligible",
                record.get(
                    "publishable",
                    False,
                ),
            )
        )
        for record in weekly_records
    )

    delivered = sum(
        bool(
            record.get(
                "delivered",
                False,
            )
        )
        for record in weekly_records
    )

    logger.info(
        "weekly_report_started "
        "settled=%s eligible=%s delivered=%s "
        "period_days=%s",
        len(
            weekly_records
        ),
        eligible,
        delivered,
        REPORT_PERIOD_DAYS,
    )

    stamp = now.strftime(
        "%Y-%m-%d"
    )

    path = create_weekly_report(
        weekly_records,
        settings.report_dir
        / f"weekly-{stamp}.png",
    )

    client = TelegramClient(
        settings.report_token,
        settings.report_chat_id,
    )

    if not client.enabled:
        logger.error(
            "weekly_report_delivery_failed "
            "reason=missing_telegram_credentials "
            "path=%s",
            path,
        )

        return 1

    sent = client.send_photo(
        path,
        "SuperLig-AL haftalık raporu",
    )

    if not sent:
        logger.error(
            "weekly_report_delivery_failed "
            "reason=telegram_api_rejected "
            "path=%s",
            path,
        )

        return 1

    logger.info(
        "weekly_report_completed "
        "path=%s settled=%s "
        "eligible=%s delivered=%s",
        path,
        len(
            weekly_records
        ),
        eligible,
        delivered,
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(
        main()
    )
