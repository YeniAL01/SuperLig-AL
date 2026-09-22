"""Premium Telegram match-card renderer for Süper Lig predictions."""
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
from io import BytesIO

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

BG = "#041322"; PANEL = "#071e33"; BORDER = "#18b7ff"; WHITE = "#f5f8fc"
MUTED = "#a9bdd0"; GREEN = "#42e77b"; GOLD = "#ffc83d"; RED = "#ff4056"; BLUE = "#28b7ff"
TZ = ZoneInfo("Europe/Istanbul")


def _font(size, bold=False, italic=False):
    candidates=[]
    if italic: candidates += ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf']
    candidates += ['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf']
    for name in candidates:
        try: return ImageFont.truetype(name,size)
        except OSError: pass
    return ImageFont.load_default()


def _center(draw, box, text, font, fill):
    l,t,r,b=draw.textbbox((0,0),str(text),font=font)
    draw.text(((box[0]+box[2]-(r-l))/2,(box[1]+box[3]-(b-t))/2-t/2),str(text),font=font,fill=fill)


def _dt(kickoff):
    try: return datetime.fromisoformat(str(kickoff).replace('Z','+00:00')).astimezone(TZ)
    except Exception: return None


def _time(kickoff):
    dt=_dt(kickoff); return dt.strftime('%H:%M') if dt else str(kickoff or '—')


def _fit(text, max_chars=18):
    text=str(text).upper()
    return text if len(text)<=max_chars else text[:max_chars-1]+'…'


def _logo(team_id, size=94):
    if not team_id: return None
    url=f"https://images.fotmob.com/image_resources/logo/teamlogo/{team_id}.png"
    try:
        response=requests.get(url,timeout=8,headers={'User-Agent':'Mozilla/5.0'})
        response.raise_for_status()
        logo=Image.open(BytesIO(response.content)).convert('RGBA')
        logo.thumbnail((size,size),Image.Resampling.LANCZOS)
        return logo
    except Exception:
        return None


def _paste_logo(image, draw, cx, cy, team, team_id):
    logo=_logo(team_id)
    if logo:
        image.alpha_composite(logo,(int(cx-logo.width/2),int(cy-logo.height/2)))
        return
    draw.ellipse((cx-42,cy-42,cx+42,cy+42),fill='#0b3553',outline=BLUE,width=2)
    initials=''.join(w[0] for w in str(team).split()[:2]).upper() or '?'
    _center(draw,(cx-42,cy-42,cx+42,cy+42),initials,_font(25,True),WHITE)


def _stadium_background(width,height):
    base=Image.new('RGBA',(width,height),BG); d=ImageDraw.Draw(base)
    # restrained stadium/pitch atmosphere; keeps the data cards dominant
    pitch_y=height-125
    d.rectangle((0,pitch_y,width,height),fill=(4,38,43,255))
    for y in range(pitch_y, height, 18):
        d.line((0,y,width,y),fill=(20,78,70,65),width=1)
    d.line((width//2,pitch_y,width//2,height),fill=(40,126,108,80),width=1)
    d.arc((width//2-95,pitch_y+15,width//2+95,pitch_y+205),180,360,fill=(40,126,108,80),width=1)
    d.line((0,pitch_y,width,pitch_y),fill=(24,183,255,80),width=1)
    return base


def _card(image, draw, box, row, index):
    x1,y1,x2,y2=box
    # glow + panel
    glow=Image.new('RGBA',image.size,(0,0,0,0)); gd=ImageDraw.Draw(glow)
    gd.rounded_rectangle(box,22,outline=(24,183,255,130),width=8)
    glow=glow.filter(ImageFilter.GaussianBlur(8)); image.alpha_composite(glow)
    draw.rounded_rectangle(box,22,fill=PANEL,outline=BORDER,width=2)
    draw.rounded_rectangle((x1+18,y1+16,x1+65,y1+61),8,fill='#075383')
    _center(draw,(x1+18,y1+16,x1+65,y1+61),str(index),_font(22,True),WHITE)
    draw.text((x1+86,y1+24),f"◷  {_time(row.get('kickoff'))}",font=_font(22,True),fill=WHITE)
    draw.line((x1+26,y1+75,x2-26,y1+75),fill='#21445f',width=1)

    fixture=row.get('fixture',''); home,away=(fixture.split(' - ',1)+[''])[:2]
    left_cx=x1+155; right_cx=x2-155; logo_y=y1+140
    _paste_logo(image,draw,left_cx,logo_y,home,row.get('home_team_id'))
    _paste_logo(image,draw,right_cx,logo_y,away,row.get('away_team_id'))
    _center(draw,(left_cx-125,y1+190,left_cx+125,y1+228),_fit(home),_font(17,True),WHITE)
    _center(draw,(right_cx-125,y1+190,right_cx+125,y1+228),_fit(away),_font(17,True),WHITE)
    _center(draw,(x1+280,y1+112,x2-280,y1+185),'VS',_font(29,True),WHITE)

    conf=float(row.get('confidence',0)); low=conf<58; color=RED if low else GREEN
    bar=(x1+24,y1+238,x2-24,y1+302)
    draw.rounded_rectangle(bar,14,fill='#351218' if low else '#082c25',outline=color,width=2)
    draw.text((x1+50,y1+255),'▥  Başarı Oranı',font=_font(18,True),fill=WHITE)
    draw.text((x1+245,y1+246),f"%{conf:.1f}",font=_font(32,True),fill=color)
    if low:
        draw.rounded_rectangle((x2-185,y1+248,x2-42,y1+291),10,fill='#4a1119')
        draw.text((x2-169,y1+259),'!  DÜŞÜK GÜVEN',font=_font(12,True),fill=RED)

    draw.line((x1+315,y1+318,x1+315,y2-22),fill='#21445f',width=1)
    draw.text((x1+38,y1+326),'♛  Kazanan Takım:',font=_font(16),fill=WHITE)
    draw.text((x1+38,y1+356),str(row.get('winner','—')),font=_font(18,True),fill=GOLD)
    draw.text((x1+340,y1+326),'↗  2.5 Alt/Üst:',font=_font(16),fill=WHITE)
    ou=str(row.get('ou25','—'))
    draw.text((x1+340,y1+356),ou,font=_font(19,True),fill=GREEN if ou=='ÜST' else RED)


def _signature_badge(draw,cx,cy):
    r=48
    draw.ellipse((cx-r,cy-r,cx+r,cy+r),fill='#061522',outline=GOLD,width=3)
    draw.ellipse((cx-r+6,cy-r+6,cx+r-6,cy+r-6),outline='#a77d25',width=1)
    draw.text((cx,cy-r+13),'DESIGNED BY',font=_font(7,True),fill=GOLD,anchor='mm')
    crown=[(cx-14,cy-15),(cx-11,cy-28),(cx-4,cy-20),(cx,cy-32),(cx+5,cy-20),(cx+13,cy-28),(cx+11,cy-15)]
    draw.polygon(crown,fill=GOLD); draw.rectangle((cx-14,cy-15,cx+11,cy-11),fill=GOLD)
    draw.text((cx,cy+5),'Sercan',font=_font(18,italic=True),fill=WHITE,anchor='mm')
    draw.line((cx-28,cy+20,cx+28,cy+20),fill=GOLD,width=2)
    draw.text((cx,cy+33),'VERİ • ANALİZ',font=_font(6,True),fill=GOLD,anchor='mm')


def create_prediction_table(rows,output:Path):
    if not rows: raise ValueError('At least one prediction is required')
    # renderer is defensive: correct order even if caller passes unsorted rows
    rows=sorted(rows,key=lambda r:(_dt(r.get('kickoff')) or datetime.max.replace(tzinfo=TZ),-float(r.get('confidence',0))))
    width=1400; header=172; footer=130; gap=22; margin=30
    cols=1 if len(rows)==1 else 2; card_w=(width-2*margin-gap*(cols-1))//cols; card_h=405
    grid_rows=(len(rows)+cols-1)//cols; height=header+grid_rows*card_h+(grid_rows-1)*gap+footer
    image=_stadium_background(width,height); draw=ImageDraw.Draw(image)
    draw.text((48,27),'SÜPER LİG',font=_font(36,True),fill=WHITE)
    draw.text((48,70),'MAÇ TAHMİNLERİ',font=_font(44,True),fill=BLUE)
    draw.text((50,128),'VERİ  •  ANALİZ  •  YAPAY ZEKA',font=_font(16),fill=BLUE)
    dates=[_dt(r.get('kickoff')) for r in rows if _dt(r.get('kickoff'))]
    if dates:
        label=min(dates).strftime('%d.%m.%Y')+'  •  TÜRKİYE SAATİ'
        draw.text((width-48,42),label,font=_font(16,True),fill=WHITE,anchor='ra')
    for i,row in enumerate(rows):
        rr=i//cols; cc=i%cols; x=margin+cc*(card_w+gap); y=header+rr*(card_h+gap)
        _card(image,draw,(x,y,x+card_w,y+card_h),row,i+1)
    fy=height-footer+42
    draw.text((48,fy),'▥  VERİ GÜCÜ     ◉  YAPAY ZEKA DESTEĞİ     ◎  DAHA İSABETLİ TAHMİNLER',font=_font(15,True),fill=MUTED)
    _signature_badge(draw,width-82,height-64)
    output=Path(output); output.parent.mkdir(parents=True,exist_ok=True); image.convert('RGB').save(output,'PNG',quality=95); return output
