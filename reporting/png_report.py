"""Premium weekly and season AI-performance PNG reports."""
from __future__ import annotations
from pathlib import Path
from typing import Any
from PIL import Image, ImageDraw, ImageFont

BG='#061523'; PANEL='#0b2133'; BORDER='#1678b7'; WHITE='#f5f8fc'; MUTED='#9db6c9'; CYAN='#16b8ff'; GREEN='#47ef82'; RED='#ff4655'; GOLD='#ffc52f'


def _font(size,bold=False,italic=False):
    if italic:
        names=['/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf','DejaVuSans-Oblique.ttf']
    else:
        names=['/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf','DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf']
    for n in names:
        try:return ImageFont.truetype(n,size)
        except OSError:pass
    return ImageFont.load_default(size=size)


def _correct(r,key):
    mc=r.get('market_correct',{})
    if key in mc:return bool(mc[key])
    if key=='1x2':return bool(r.get('winner_correct'))
    if key=='score':return bool(r.get('score_correct'))
    return bool(r.get(f'{key}_correct'))


def _stats(records,key):
    n=len(records); c=sum(_correct(r,key) for r in records); return c,n,(100*c/n if n else 0.0)


def _signature(d,w,h):
    # Same compact rubber-stamp identity used on prediction cards.
    cx,cy=w-86,h-67; r=50
    d.ellipse((cx-r,cy-r,cx+r,cy+r),outline=GOLD,width=3)
    d.ellipse((cx-r+6,cy-r+6,cx+r-6,cy+r-6),outline='#b58b2d',width=2)
    for a,b in [((-42,-20),(-38,-18)),((35,-30),(39,-27)),((-28,38),(-23,40)),((26,40),(31,38))]:
        d.line((cx+a[0],cy+a[1],cx+b[0],cy+b[1]),fill=BG,width=3)
    crown=[(cx-14,cy-14),(cx-11,cy-28),(cx-4,cy-20),(cx,cy-32),(cx+5,cy-20),(cx+13,cy-28),(cx+11,cy-14)]
    d.polygon(crown,fill=GOLD); d.rectangle((cx-14,cy-14,cx+11,cy-10),fill=GOLD)
    d.text((cx,cy-r+11),'DESIGNED BY',font=_font(6,True),fill=GOLD,anchor='mm')
    d.text((cx,cy+6),'Sercan',font=_font(18,italic=True),fill=WHITE,anchor='mm')
    d.line((cx-29,cy+20,cx+29,cy+20),fill=GOLD,width=2)
    d.text((cx,cy+33),'VERİ • ANALİZ • YAPAY ZEKA',font=_font(5,True),fill=GOLD,anchor='mm')


def _header(d,title,subtitle,w):
    d.text((38,28),'SÜPER LİG',font=_font(29,True),fill=WHITE); d.text((260,25),title,font=_font(35,True),fill=CYAN); d.text((260,70),subtitle,font=_font(15,True),fill=MUTED); d.line((38,105,w-38,105),fill=BORDER,width=2)


def _summary_cards(d,records,y,w):
    keys=[('1x2','KAZANAN (1X2)'),('ou25','ALT / ÜST 2.5'),('btts','KG VAR / YOK'),('score','TAM SKOR')]
    gap=14; x0=38; cw=(w-76-gap*3)//4
    for i,(key,label) in enumerate(keys):
        x=x0+i*(cw+gap); c,n,p=_stats(records,key)
        d.rounded_rectangle((x,y,x+cw,y+118),radius=16,fill=PANEL,outline=GREEN if p>=50 else RED,width=2)
        d.text((x+16,y+15),label,font=_font(17,True),fill=WHITE); d.text((x+16,y+48),f'{c} / {n}',font=_font(22,True),fill=WHITE); d.text((x+16,y+78),f'%{p:.0f}',font=_font(27,True),fill=GREEN if p>=50 else RED)


def create_weekly_report(records:list[dict[str,Any]],output:Path)->Path:
    w=1400; row_h=58; h=max(760,420+len(records)*row_h)
    im=Image.new('RGB',(w,h),BG); d=ImageDraw.Draw(im); _header(d,'HAFTALIK AL PERFORMANSI','TAHMİN • GERÇEK SONUÇ • PUAN',w)
    d.rounded_rectangle((38,125,w-38,185),radius=12,fill='#10283d',outline=BORDER,width=1)
    headers=[(52,'MAÇ'),(430,'TAHMİN'),(690,'GERÇEK'),(840,'1X2'),(930,'A / Ü'),(1020,'KG'),(1110,'SKOR'),(1210,'PUAN')]
    for x,t in headers:d.text((x,143),t,font=_font(16,True),fill=MUTED)
    y=190
    for r in records:
        d.rectangle((38,y,w-38,y+row_h),fill=PANEL if (y//row_h)%2 else '#0d273b')
        fixture=str(r.get('fixture','-')); pred=f"{r.get('home_goals','-')}-{r.get('away_goals','-')}"; actual=f"{r.get('actual_home','-')}-{r.get('actual_away','-')}"
        d.text((52,y+18),fixture,font=_font(15,True),fill=WHITE); d.text((430,y+18),pred,font=_font(17,True),fill=WHITE); d.text((690,y+18),actual,font=_font(17,True),fill=WHITE)
        for x,key in [(850,'1x2'),(940,'ou25'),(1030,'btts'),(1120,'score')]: d.text((x,y+15),'✓' if _correct(r,key) else '✕',font=_font(23,True),fill=GREEN if _correct(r,key) else RED)
        pts=int(r.get('points',10*sum(_correct(r,k) for k in ('1x2','ou25','btts','score')))); d.text((1210,y+18),f'{pts}/40',font=_font(17,True),fill=GOLD)
        y+=row_h
    total=sum(int(r.get('points',10*sum(_correct(r,k) for k in ('1x2','ou25','btts','score')))) for r in records); maximum=40*len(records); pct=100*total/maximum if maximum else 0
    d.text((40,y+24),f'HAFTA GENELİ  •  {total} / {maximum} PUAN  •  %{pct:.1f}',font=_font(25,True),fill=CYAN); _summary_cards(d,records,y+70,w); _signature(d,w,h)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);im.save(output,'PNG');return output


def create_season_report(records:list[dict[str,Any]],output:Path)->Path:
    w,h=1400,650; im=Image.new('RGB',(w,h),BG); d=ImageDraw.Draw(im); _header(d,'SEZON GENELİ AL PERFORMANSI','TOPLAM VERİ • GERÇEK SONUÇLAR • 4 HAFTALIK GELİŞİM',w)
    total=sum(int(r.get('points',10*sum(_correct(r,k) for k in ('1x2','ou25','btts','score')))) for r in records); maximum=40*len(records); pct=100*total/maximum if maximum else 0
    d.rounded_rectangle((38,135,w-38,280),radius=18,fill=PANEL,outline=BORDER,width=2); d.text((70,160),'SEZON GENELİ',font=_font(22,True),fill=WHITE); d.text((70,202),f'{total} / {maximum} PUAN',font=_font(35,True),fill=GOLD); d.text((560,188),f'%{pct:.1f}',font=_font(58,True),fill=CYAN); d.text((860,205),f'Değerlendirilen maç: {len(records)}',font=_font(22,True),fill=WHITE)
    _summary_cards(d,records,320,w); d.text((40,480),'AL geliştirmesi için değerlendirme penceresi: 4 haftalık gerçek tahmin süreci',font=_font(19,True),fill=MUTED); _signature(d,w,h)
    output=Path(output);output.parent.mkdir(parents=True,exist_ok=True);im.save(output,'PNG');return output
