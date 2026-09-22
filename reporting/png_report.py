"""Premium single-image weekly + season AI-performance report."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


BG = "#061523"
PANEL = "#0b2133"
PANEL2 = "#0d273b"
BORDER = "#1678b7"
WHITE = "#f5f8fc"
MUTED = "#9db6c9"
CYAN = "#16b8ff"
GREEN = "#47ef82"
RED = "#ff4655"
GOLD = "#ffc52f"


def _font(size, bold=False, italic=False):
    if italic:
        names = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
            "DejaVuSans-Oblique.ttf",
        ]
    else:
        names = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf",
        ]
    for n in names:
        try:
            return ImageFont.truetype(n, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _correct(r, key):
    mc = r.get("market_correct", {})
    if key in mc:
        return bool(mc[key])
    if key == "1x2":
        return bool(r.get("winner_correct"))
    if key == "score":
        return bool(r.get("score_correct"))
    return bool(r.get(f"{key}_correct"))


def _stats(records, key):
    n = len(records)
    c = sum(_correct(r, key) for r in records)
    return c, n, (100 * c / n if n else 0.0)


def _points(r):
    return int(
        r.get(
            "points",
            10 * sum(_correct(r, k) for k in ("1x2", "ou25", "btts", "score")),
        )
    )


def _totals(records):
    total = sum(_points(r) for r in records)
    maximum = 40 * len(records)
    return total, maximum, (100 * total / maximum if maximum else 0.0)


def _rr(d, box, r=14, fill=PANEL, outline=BORDER, width=2):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=width)


def _signature(d, w, h):
    # Small stamp, fully below the upper footer rule.
    cx, cy = w - 72, h - 66
    r = 43
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=GOLD, width=3)
    d.ellipse(
        (cx - r + 5, cy - r + 5, cx + r - 5, cy + r - 5),
        outline="#b58b2d",
        width=2,
    )
    crown = [
        (cx - 12, cy - 13),
        (cx - 9, cy - 25),
        (cx - 3, cy - 18),
        (cx, cy - 29),
        (cx + 4, cy - 18),
        (cx + 11, cy - 25),
        (cx + 9, cy - 13),
    ]
    d.polygon(crown, fill=GOLD)
    d.rectangle((cx - 12, cy - 13, cx + 9, cy - 9), fill=GOLD)
    d.text(
        (cx, cy - r + 10),
        "DESIGNED BY",
        font=_font(5, True),
        fill=GOLD,
        anchor="mm",
    )
    d.text(
        (cx, cy + 5),
        "Sercan",
        font=_font(15, italic=True),
        fill=WHITE,
        anchor="mm",
    )
    d.line((cx - 25, cy + 18, cx + 25, cy + 18), fill=GOLD, width=2)
    d.text(
        (cx, cy + 30),
        "VERİ • ANALİZ • YAPAY ZEKA",
        font=_font(4, True),
        fill=GOLD,
        anchor="mm",
    )


def _summary_cards(d, records, y, w, x0=38, right=None, height=100):
    right = right or w - 38
    keys = [
        ("1x2", "KAZANAN (1X2)"),
        ("ou25", "ALT / ÜST 2.5"),
        ("btts", "KG VAR / YOK"),
        ("score", "TAM SKOR"),
    ]
    gap = 12
    cw = (right - x0 - gap * 3) // 4
    for i, (key, label) in enumerate(keys):
        x = x0 + i * (cw + gap)
        c, n, p = _stats(records, key)
        col = GREEN if p >= 50 else RED
        _rr(d, (x, y, x + cw, y + height), 12, PANEL, col, 2)

        # Keep all three lines safely inside short weekly cards as well as
        # the taller season cards.
        label_y = y + 10
        count_y = y + 34
        pct_y = y + height - 27

        d.text((x + 14, label_y), label, font=_font(14, True), fill=WHITE)
        d.text((x + 14, count_y), f"{c} / {n}", font=_font(18, True), fill=WHITE)
        d.text((x + 14, pct_y), f"%{p:.0f}", font=_font(21, True), fill=col)


def _parse_dt(row):
    for key in ("kickoff", "datetime", "date", "created_at"):
        raw = row.get(key)
        if not raw:
            continue
        try:
            return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except ValueError:
            pass
    return None


def _trend(records):
    groups = defaultdict(list)
    for r in records:
        dt = _parse_dt(r)
        if dt:
            iso = dt.isocalendar()
            groups[(iso.year, iso.week)].append(r)

    vals = []
    for key in sorted(groups)[-4:]:
        _, _, pct = _totals(groups[key])
        vals.append(pct)
    return vals


def _assessment(records):
    s = {k: _stats(records, k)[2] for k in ("1x2", "ou25", "btts", "score")}
    best = max(s, key=s.get)
    worst = min(s, key=s.get)
    labels = {
        "1x2": "1X2",
        "ou25": "Alt/Üst",
        "btts": "KG",
        "score": "Tam Skor",
    }
    return (
        f"En güçlü alan: {labels[best]} (%{s[best]:.0f}). "
        f"Gelişim alanı: {labels[worst]} (%{s[worst]:.0f}). "
        "4 haftalık gerçek tahmin verisi biriktikçe model optimizasyonu "
        "bu performans dağılımına göre değerlendirilecektir."
    )


def create_combined_report(
    weekly: list[dict[str, Any]],
    season: list[dict[str, Any]],
    output: Path,
    week_label: str = "HAFTA",
) -> Path:
    w = 1400
    row_h = 47

    weekly_top = 150
    weekly_title_h = 58
    table_header_h = 45
    table_header_gap = 3

    # Explicit vertical layout prevents the final match, HAFTA GENELİ and
    # weekly summary cards from colliding.
    table_header_y = weekly_top + weekly_title_h
    rows_y = table_header_y + table_header_h + table_header_gap
    rows_bottom = rows_y + len(weekly) * row_h

    weekly_summary_gap = 20
    summary_title_h = 30
    summary_cards_gap = 10
    weekly_card_h = 88
    weekly_bottom_pad = 18

    summary_y = rows_bottom + weekly_summary_gap
    weekly_cards_y = summary_y + summary_title_h + summary_cards_gap
    weekly_bottom = weekly_cards_y + weekly_card_h + weekly_bottom_pad

    season_top = weekly_bottom + 24
    season_h = 190
    lower_top = season_top + season_h + 20
    lower_h = 230
    footer_h = 115
    h = lower_top + lower_h + footer_h

    im = Image.new("RGB", (w, h), BG)
    d = ImageDraw.Draw(im)

    d.text((38, 28), "SÜPER LİG", font=_font(28, True), fill=WHITE)
    d.text((38, 62), "AL PERFORMANS RAPORU", font=_font(36, True), fill=CYAN)
    d.text(
        (38, 108),
        "TAHMİN  •  GERÇEK SONUÇ  •  ANALİZ  •  GELİŞİM",
        font=_font(14, True),
        fill=CYAN,
    )
    d.text(
        (w - 38, 52),
        week_label,
        font=_font(19, True),
        fill=WHITE,
        anchor="ra",
    )
    d.line((38, 132, w - 38, 132), fill=CYAN, width=2)

    # Weekly panel
    _rr(d, (20, weekly_top, w - 20, weekly_bottom), 16, BG, CYAN, 2)
    d.text(
        (40, weekly_top + 15),
        "HAFTALIK AL PERFORMANSI",
        font=_font(27, True),
        fill=CYAN,
    )

    y = table_header_y
    _rr(d, (38, y, w - 38, y + table_header_h), 10, "#10283d", BORDER, 1)
    heads = [
        (52, "#"),
        (90, "MAÇ"),
        (430, "TAHMİN"),
        (565, "GERÇEK"),
        (665, "1X2"),
        (755, "A / Ü"),
        (845, "KG"),
        (935, "SKOR"),
        (1035, "PUAN"),
    ]
    for x, t in heads:
        d.text((x, y + 13), t, font=_font(13, True), fill=MUTED)

    y = rows_y
    for idx, r in enumerate(weekly, 1):
        d.rectangle(
            (38, y, w - 38, y + row_h - 2),
            fill=PANEL if idx % 2 else PANEL2,
        )
        fixture = str(r.get("fixture", "-"))
        pred = f"{r.get('home_goals', '-')}-{r.get('away_goals', '-')}"
        actual = f"{r.get('actual_home', '-')}-{r.get('actual_away', '-')}"

        d.text((52, y + 13), str(idx), font=_font(13, True), fill=WHITE)
        d.text((90, y + 13), fixture, font=_font(13, True), fill=WHITE)
        d.text((430, y + 13), pred, font=_font(14, True), fill=WHITE)
        d.text((565, y + 13), actual, font=_font(14, True), fill=WHITE)

        for x, key in [
            (675, "1x2"),
            (765, "ou25"),
            (855, "btts"),
            (945, "score"),
        ]:
            ok = _correct(r, key)
            d.text(
                (x, y + 10),
                "✓" if ok else "✕",
                font=_font(20, True),
                fill=GREEN if ok else RED,
            )

        d.text(
            (1035, y + 13),
            f"{_points(r)}/40",
            font=_font(14, True),
            fill=GOLD,
        )
        y += row_h

    wt, wm, wp = _totals(weekly)
    d.text(
        (40, summary_y),
        f"HAFTA GENELİ   {wt} / {wm} PUAN   %{wp:.1f}",
        font=_font(24, True),
        fill=CYAN,
    )
    _summary_cards(
        d,
        weekly,
        weekly_cards_y,
        w,
        x0=420,
        right=w - 38,
        height=weekly_card_h,
    )

    # Season panel
    _rr(d, (20, season_top, w - 20, season_top + season_h), 16, BG, CYAN, 2)
    d.text(
        (40, season_top + 16),
        "SEZON GENELİ AL PERFORMANSI",
        font=_font(27, True),
        fill=CYAN,
    )
    st, sm, sp = _totals(season)
    d.text((45, season_top + 68), "SEZON GENELİ", font=_font(18, True), fill=WHITE)
    d.text(
        (45, season_top + 103),
        f"{st} / {sm} PUAN",
        font=_font(30, True),
        fill=GOLD,
    )
    d.text((45, season_top + 142), f"%{sp:.1f}", font=_font(30, True), fill=CYAN)
    d.text(
        (235, season_top + 151),
        f"Değerlendirilen maç: {len(season)}",
        font=_font(13),
        fill=MUTED,
    )
    _summary_cards(
        d,
        season,
        season_top + 70,
        w,
        x0=420,
        right=w - 38,
        height=100,
    )

    # Trend
    left = (20, lower_top, 750, lower_top + lower_h)
    _rr(d, left, 16, BG, CYAN, 2)
    d.text(
        (42, lower_top + 18),
        "4 HAFTALIK GELİŞİM",
        font=_font(21, True),
        fill=CYAN,
    )
    vals = _trend(season)
    chart_x0 = 85
    chart_y0 = lower_top + 185
    chart_h = 105
    bw = 100
    gap = 45
    d.line((chart_x0, lower_top + 68, chart_x0, chart_y0), fill=MUTED, width=1)
    d.line((chart_x0, chart_y0, 700, chart_y0), fill=MUTED, width=1)

    if vals:
        start = chart_x0 + 35
        for i, v in enumerate(vals):
            bh = max(2, int(chart_h * v / 100))
            x = start + i * (bw + gap)
            d.rounded_rectangle(
                (x, chart_y0 - bh, x + bw, chart_y0),
                radius=6,
                fill="#118fe0",
            )
            d.text(
                (x + bw / 2, chart_y0 - bh - 20),
                f"%{v:.1f}",
                font=_font(13, True),
                fill=WHITE,
                anchor="mm",
            )
            d.text(
                (x + bw / 2, chart_y0 + 15),
                f"Hafta {i + 1}",
                font=_font(12),
                fill=MUTED,
                anchor="ma",
            )
    else:
        d.text(
            (100, lower_top + 115),
            "Haftalık gerçek tahmin verisi biriktikçe trend burada oluşacaktır.",
            font=_font(14),
            fill=MUTED,
        )

    # Assessment
    _rr(d, (770, lower_top, w - 20, lower_top + lower_h), 16, BG, CYAN, 2)
    d.text(
        (792, lower_top + 18),
        "KISA DEĞERLENDİRME",
        font=_font(21, True),
        fill=CYAN,
    )
    assessment = _assessment(weekly)
    words = assessment.split()
    lines = []
    line = ""
    assessment_font = _font(14)

    for word in words:
        test = (line + " " + word).strip()
        if d.textlength(test, font=assessment_font) > 545:
            lines.append(line)
            line = word
        else:
            line = test

    if line:
        lines.append(line)

    yy = lower_top + 62
    for line in lines[:7]:
        d.text((792, yy), line, font=assessment_font, fill=WHITE)
        yy += 25

    # Footer: stamp is below the top rule and never overlaps content.
    fy = lower_top + lower_h + 28
    d.line((38, fy, w - 38, fy), fill=BORDER, width=1)
    d.text(
        (38, fy + 38),
        "VERİ GÜCÜ   •   YAPAY ZEKA DESTEĞİ   •   DAHA İSABETLİ TAHMİNLER",
        font=_font(13, True),
        fill=MUTED,
    )
    d.text(
        (700, fy + 38),
        "Futbolun Verisi, Daha Net Tahminler...",
        font=_font(14, italic=True),
        fill=WHITE,
    )
    _signature(d, w, h)

    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    im.save(output, "PNG")
    return output


# Compatibility helpers kept for imports outside report.py.
def create_weekly_report(records, output):
    return create_combined_report(records, records, output, "HAFTALIK RAPOR")


def create_season_report(records, output):
    return create_combined_report(records, records, output, "SEZON RAPORU")
