"""Premium Telegram match-card renderer for Süper Lig predictions."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BG = "#061525"; PANEL = "#0b2238"; BORDER = "#1e9ce8"; WHITE = "#f5f8fc"
MUTED = "#a9bdd0"; GREEN = "#45e57b"; GOLD = "#ffc83d"; RED = "#ff4d5f"; BLUE = "#2db5ff"


def _font(size, bold=False, italic=False):
    candidates = []
    if italic:
        candidates += ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf']
    candidates += [
        '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
        'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf',
    ]
    for name in candidates:
        try: return ImageFont.truetype(name, size)
        except OSError: pass
    return ImageFont.load_default()


def _center(draw, box, text, font, fill):
    l,t,r,b = draw.textbbox((0,0), str(text), font=font)
    x=(box[0]+box[2]-(r-l))/2; y=(box[1]+box[3]-(b-t))/2-(t/2)
    draw.text((x,y), str(text), font=font, fill=fill)


def _time(kickoff):
    try:
        dt=datetime.fromisoformat(str(kickoff).replace('Z','+00:00'))
        return dt.astimezone(ZoneInfo('Europe/Istanbul')).strftime('%H:%M')
    except Exception: return str(kickoff or '—')


def _card(draw, box, row, index):
    x1,y1,x2,y2=box
    draw.rounded_rectangle(box, 24, fill=PANEL, outline=BORDER, width=2)
    draw.rounded_rectangle((x1+18,y1+18,x1+64,y1+62), 8, fill='#0e4d78')
    _center(draw,(x1+18,y1+18,x1+64,y1+62),str(index),_font(22,True),WHITE)
    fixture=row['fixture']; home, away=(fixture.split(' - ',1)+[''])[:2]
    _center(draw,(x1+70,y1+28,x2-70,y1+78),f"{home.upper()}  VS  {away.upper()}",_font(24,True),WHITE)
    draw.line((x1+28,y1+92,x2-28,y1+92),fill='#21445f',width=1)
    draw.text((x1+38,y1+112),f"🕐  {_time(row.get('kickoff'))}",font=_font(20),fill=WHITE)
    conf=float(row.get('confidence',0)); low=conf<58
    color=RED if low else GREEN
    draw.rounded_rectangle((x1+28,y1+158,x2-28,y1+224),16,fill='#092d28' if not low else '#32151b',outline=color,width=2)
    draw.text((x1+50,y1+174),'Başarı Oranı',font=_font(20,True),fill=WHITE)
    draw.text((x2-180,y1+164),f"%{conf:.1f}",font=_font(34,True),fill=color)
    if low: draw.text((x2-300,y1+208),'🚨 DÜŞÜK GÜVEN',font=_font(14,True),fill=RED)
    draw.text((x1+42,y1+258),'🏆  Kazanan Takım:',font=_font(20),fill=WHITE)
    draw.text((x1+285,y1+258),row.get('winner','—'),font=_font(21,True),fill=GOLD)
    draw.text((x1+42,y1+306),'⚽  2.5 Alt/Üst:',font=_font(20),fill=WHITE)
    draw.text((x1+285,y1+306),row.get('ou25','—'),font=_font(21,True),fill=GREEN if row.get('ou25')=='ÜST' else RED)


def _signature_badge(draw, cx, cy):
    r=47
    draw.ellipse((cx-r,cy-r,cx+r,cy+r),outline=GOLD,width=3)
    draw.ellipse((cx-r+6,cy-r+6,cx+r-6,cy+r-6),outline='#b58b31',width=1)
    draw.text((cx,cy-r+12),'DESIGNED BY',font=_font(7,True),fill=GOLD,anchor='mm')
    crown=[(cx-14,cy-14),(cx-11,cy-27),(cx-4,cy-19),(cx,cy-31),(cx+5,cy-19),(cx+13,cy-27),(cx+11,cy-14)]
    draw.polygon(crown,fill=GOLD)
    draw.rectangle((cx-14,cy-14,cx+11,cy-10),fill=GOLD)
    draw.text((cx,cy+5),'Sercan',font=_font(19,italic=True),fill=WHITE,anchor='mm')
    draw.line((cx-28,cy+20,cx+28,cy+20),fill=GOLD,width=2)
    draw.text((cx,cy+33),'VERİ • ANALİZ',font=_font(6,True),fill=GOLD,anchor='mm')

def create_prediction_table(rows, output: Path):
    if not rows: raise ValueError('At least one prediction is required')
    width=1400; header=190; footer=110; gap=22; margin=42
    cols=1 if len(rows)==1 else 2
    card_w=(width-2*margin-gap*(cols-1))//cols; card_h=370
    grid_rows=(len(rows)+cols-1)//cols
    height=header+grid_rows*card_h+(grid_rows-1)*gap+footer
    image=Image.new('RGB',(width,height),BG); d=ImageDraw.Draw(image)
    d.text((55,35),'SÜPER LİG',font=_font(38,True),fill=WHITE)
    d.text((55,82),'MAÇ TAHMİNLERİ',font=_font(46,True),fill=BLUE)
    d.text((57,142),'VERİ  •  ANALİZ  •  YAPAY ZEKA',font=_font(17),fill=BLUE)
    for i,row in enumerate(rows):
        rr=i//cols; cc=i%cols; x=margin+cc*(card_w+gap); y=header+rr*(card_h+gap)
        _card(d,(x,y,x+card_w,y+card_h),row,i+1)
    fy=height-footer+28
    d.text((55,fy),'VERİ GÜCÜ   •   YAPAY ZEKA DESTEĞİ   •   DAHA İSABETLİ TAHMİNLER',font=_font(16,True),fill=MUTED)
    _signature_badge(d,width-92,height-58)
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True); image.save(output,'PNG'); return output
