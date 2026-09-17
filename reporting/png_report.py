"""Generate a portable weekly PNG performance report."""

from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


MARKETS = (
    ("1x2", "1X2"),
    ("ou25", "2.5"),
    ("btts", "KG"),
)


def _percentage(
    correct: int,
    total: int,
) -> str:
    if total <= 0:
        return "-"

    return (
        f"%{correct / total * 100:.1f}"
    )


def _market_stats(
    records: list[dict[str, Any]],
    market: str,
) -> tuple[int, int]:
    total = 0
    correct = 0

    for record in records:
        markets = record.get(
            "markets",
            {}
        )

        if not isinstance(
            markets,
            dict,
        ):
            continue

        result = markets.get(
            market
        )

        if not isinstance(
            result,
            dict,
        ):
            continue

        value = result.get(
            "correct"
        )

        if value is None:
            continue

        total += 1

        if bool(value):
            correct += 1

    return correct, total


def create_weekly_report(
    records: list[dict[str, Any]],
    output: Path,
) -> Path:
    """Render settled results and distinguish eligibility from delivery."""

    width = 1400
    row_height = 42

    height = max(
        470,
        315
        + len(records)
        * row_height,
    )

    image = Image.new(
        "RGB",
        (
            width,
            height,
        ),
        "#101827",
    )

    draw = ImageDraw.Draw(
        image
    )

    font = ImageFont.load_default()

    total = len(
        records
    )

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
        for record in records
    )

    delivered = sum(
        bool(
            record.get(
                "delivered",
                False,
            )
        )
        for record in records
    )

    winners = sum(
        bool(
            record.get(
                "winner_correct"
            )
        )
        for record in records
    )

    scores = sum(
        bool(
            record.get(
                "score_correct"
            )
        )
        for record in records
    )

    points = sum(
        int(
            record.get(
                "points",
                0,
            )
            or 0
        )
        for record in records
    )

    winner_accuracy = (
        winners
        / total
        * 100
        if total
        else 0.0
    )

    draw.text(
        (
            35,
            25,
        ),
        "SuperLig-AL | Haftalık Performans",
        fill="white",
        font=font,
    )

    summary = (
        f"Sonuçlanan: {total}   "
        f"Uygun: {eligible}   "
        f"Telegram Teslim: {delivered}   "
        f"Doğru 1X2: {winners}   "
        f"Doğru Skor: {scores}   "
        f"Puan: {points}   "
        f"1X2 Başarı: %{winner_accuracy:.1f}"
    )

    draw.text(
        (
            35,
            70,
        ),
        summary,
        fill="#7dd3fc",
        font=font,
    )

    market_parts = []

    for market, label in MARKETS:
        correct, market_total = (
            _market_stats(
                records,
                market,
            )
        )

        market_parts.append(
            (
                f"{label}: "
                f"{correct}/{market_total} "
                f"({_percentage(correct, market_total)})"
            )
        )

    draw.text(
        (
            35,
            105,
        ),
        "Pazar Başarıları | "
        + "   ".join(
            market_parts
        ),
        fill="#a7f3d0",
        font=font,
    )

    draw.text(
        (
            35,
            150,
        ),
        (
            "Maç | Tahmin | Gerçek | "
            "Uygun | Teslim | 1X2 | Skor | Puan"
        ),
        fill="#fbbf24",
        font=font,
    )

    y = 190

    for item in records:
        is_eligible = bool(
            item.get(
                "eligible",
                item.get(
                    "publishable",
                    False,
                ),
            )
        )

        is_delivered = bool(
            item.get(
                "delivered",
                False,
            )
        )

        predicted_home = item.get(
            "home_goals",
            "-"
        )

        predicted_away = item.get(
            "away_goals",
            "-"
        )

        actual_home = item.get(
            "actual_home",
            "-"
        )

        actual_away = item.get(
            "actual_away",
            "-"
        )

        line = (
            f"{item.get('fixture', '')} | "
            f"{predicted_home}-{predicted_away} | "
            f"{actual_home}-{actual_away} | "
            f"{'E' if is_eligible else 'H'} | "
            f"{'E' if is_delivered else 'H'} | "
            f"{'✓' if item.get('winner_correct') else '✗'} | "
            f"{'✓' if item.get('score_correct') else '✗'} | "
            f"{item.get('points', 0)}"
        )

        draw.text(
            (
                35,
                y,
            ),
            line[:210],
            fill="white",
            font=font,
        )

        y += row_height

    draw.text(
        (
            35,
            height - 80,
        ),
        (
            "Uygun = yayın koşullarını sağladı. "
            "Teslim = Telegram API tarafından gerçekten kabul edildi."
        ),
        fill="#a7f3d0",
        font=font,
    )

    draw.text(
        (
            35,
            height - 45,
        ),
        (
            "Öğrenme değerlendirmesi 1X2, 2.5 Alt/Üst ve "
            "KG Var/Yok pazarlarını birbirinden bağımsız izler."
        ),
        fill="#a7f3d0",
        font=font,
    )

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    image.save(
        output,
        "PNG",
    )

    return output
