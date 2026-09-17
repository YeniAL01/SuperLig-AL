"""Generate a portable weekly PNG report."""
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFont


def create_weekly_report(records: list[dict[str, Any]], output: Path) -> Path:
    """Render settled records and distinguish eligibility from real delivery."""
    width, row_height = 1400, 42
    height = max(390, 240 + len(records) * row_height)
    image = Image.new("RGB", (width, height), "#101827")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    total = len(records)
    eligible = sum(bool(r.get("eligible", r.get("publishable", False))) for r in records)
    delivered = sum(bool(r.get("delivered", False)) for r in records)
    winners = sum(bool(r.get("winner_correct")) for r in records)
    scores = sum(bool(r.get("score_correct")) for r in records)
    points = sum(int(r.get("points", 0)) for r in records)
    accuracy = (winners / total * 100) if total else 0
    draw.text((35, 25), "SuperLig-AL | Haftalık Performans", fill="white", font=font)
    draw.text((35, 70),
              f"Toplam: {total}   Uygun: {eligible}   Telegram Teslim: {delivered}   "
              f"Doğru Kazanan: {winners}   Doğru Skor: {scores}   Puan: {points}   Başarı: %{accuracy:.1f}",
              fill="#7dd3fc", font=font)
    draw.text((35, 110), "Maç | Tahmin | Gerçek | Uygun | Teslim | Kazanan | Skor | Puan", fill="#fbbf24", font=font)
    y = 145
    for item in records:
        is_eligible = bool(item.get("eligible", item.get("publishable", False)))
        is_delivered = bool(item.get("delivered", False))
        line = (
            f"{item.get('fixture','')} | {item.get('home_goals')}-{item.get('away_goals')} | "
            f"{item.get('actual_home')}-{item.get('actual_away')} | "
            f"{'E' if is_eligible else 'H'} | {'E' if is_delivered else 'H'} | "
            f"{'✓' if item.get('winner_correct') else '✗'} | "
            f"{'✓' if item.get('score_correct') else '✗'} | {item.get('points',0)}"
        )
        draw.text((35, y), line[:210], fill="white", font=font)
        y += row_height
    insight = "Uygun = yayın koşullarını sağladı. Teslim = Telegram API tarafından gerçekten kabul edildi."
    draw.text((35, height - 45), insight, fill="#a7f3d0", font=font)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "PNG")
    return output
