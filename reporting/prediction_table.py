"""Render final predictions as one portable Telegram table image."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BLUE = '#49a5ff'
RED = '#ff6577'


def _font(size, bold=False):
    names = [
        'C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf',
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf',
    ]
    for name in names:
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


def _wrap(draw, text, font, width):
    lines, line = [], ''
    for word in str(text).split():
        candidate = f'{line} {word}'.strip()
        if line and draw.textlength(candidate, font=font) > width:
            lines.append(line)
            line = ''
        for char in word:
            candidate = line + char
            if draw.textlength(candidate, font=font) > width:
                lines.append(line)
                line = ''
            line += char
        line += ' '
    if line.strip():
        lines.append(line.strip())
    return lines or ['—']


def create_prediction_table(rows, output: Path):
    """Rows contain display strings and a verified-lineup boolean."""
    if not rows:
        raise ValueError('At least one prediction is required')
    x = [76, 432, 776, 928, 1198, 1428, 1554, 1824]
    font = _font(25)
    scratch = ImageDraw.Draw(Image.new('RGB', (1, 1)))
    wrapped = [[_wrap(scratch, value, font, x[i+1]-x[i]-36)
                for i, value in enumerate(row[:6])] for row in rows]
    heights = [max(128, 48 + 35 * max(map(len, cells))) for cells in wrapped]
    height = 384 + sum(heights)
    image = Image.new('RGB', (1900, height), '#0b1423')
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((42, 36, 1858, height-36), radius=26, fill='#132239', outline='#2b405a', width=2)
    draw.rounded_rectangle((76, 73, 84, 152), radius=4, fill='#38d6b0')
    draw.text((104, 65), 'SÜPER LİG', font=_font(43, True), fill='#f3f7fd')
    draw.text((106, 121), 'MAÇ TAHMİNLERİ', font=_font(22), fill='#abc0d7')
    draw.text((1638, 90), f'{len(rows)} MAÇ', font=_font(25, True), fill='#82ead0')
    draw.rounded_rectangle((76, 193, 1824, 251), radius=10, fill='#213650')
    for i, name in enumerate(['Maç', 'Maç sonucu', 'Güven', 'Gol tahmini', 'KG', 'Skor', 'İlk 11']):
        draw.text((x[i]+18, 207), name, font=_font(22, True), fill='#c0d0e1')
    y = 251
    for n, (row, cells, row_height) in enumerate(zip(rows, wrapped, heights)):
        if n % 2:
            draw.rectangle((76, y, 1824, y+row_height), fill='#172940')
        for i, lines in enumerate(cells):
            yy = y + (row_height-len(lines)*35)//2
            for line in lines:
                draw.text((x[i]+18, yy), line, font=font, fill='#edf3fb')
                yy += 35
        cx, cy = 1688, y+row_height//2
        if row[6]:
            draw.line([(cx-21, cy), (cx-5, cy+16), (cx+25, cy-20)], fill=BLUE, width=8)
        else:
            draw.line([(cx-18, cy-18), (cx+18, cy+18)], fill=RED, width=8)
            draw.line([(cx+18, cy-18), (cx-18, cy+18)], fill=RED, width=8)
        draw.line((76, y+row_height, 1824, y+row_height), fill='#2b405a', width=1)
        y += row_height
    draw.text((94, y+32), 'Mavi tik: İlk 11 doğrulandı   |   Kırmızı çarpı: İlk 11 doğrulanmadı', font=_font(20), fill='#adc2d8')
    draw.text((1504, y+32), 'SuperLig-AL', font=_font(22, True), fill='#adc2d8')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, format='PNG')
    return output
