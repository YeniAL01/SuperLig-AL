"""Premium weekly and season AI-performance PNG reports."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

BG='#061525'; PANEL='#0b2238'; BORDER='#1e9ce8'; WHITE='#f5f8fc'; MUTED='#a9bdd0'; GREEN='#45e57b'; RED='#ff4d5f'; BLUE='#2db5ff'; GOLD='#ffc83d'


def _font(size,bold=False,italic=False):
    names=[]
    if italic: names.append('/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf')
    names.append('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')
    for n in names:
        try:return ImageFont.truetype(n,size)
        except OSError:pass
    return ImageFont.load_default()


def _ok(v): return '✓' if v else '✕'
def _stats(records,key):
    vals=[bool(r[key]) for r in records if key in r]
    c=sum(vals); n=len(vals); return c,n,(100*c/n if n else 0)
def _points(records):
    p=sum(int(r.get('points',0) or 0) for r in records); m=40*len(records); return p,m,(100*p/m if m else 0)

def _base(title,subtitle,height):
    im=Image.new('RGB',(1500,height),BG); d=ImageDraw.Draw(im)
    d.text((50,35),title,font=_font(42,True),fill=WHITE); d.text((52,90),subtitle,font=_font(18),fill=BLUE)
    return im,d

def _signature(d,height):
    d.text((1270,height-78),'Sercan',font=_font(38,italic=True),fill=WHITE); d.line((1260,height-30,1440,height-30),fill=GOLD,width=3)

def create_weekly_report(records, output:Path):
    records=sorted(records,key=lambda r:(r.get('kickoff',''),str(r.get('fixture_id',''))))
    h=max(720,330+len(records)*58)
    im,d=_base('HAFTALIK AL PERFORMANSI','VERİ  •  ANALİZ  •  TAHMİN  •  SONUÇ',h)
    d.rounded_rectangle((35,140,1465,210),14,fill='#0d2b45',outline=BORDER,width=2)
    headers=['MAÇ','TAHMİN','GERÇEK','1X2','ALT/ÜST','KG','SKOR','PUAN']
    xs=[55,420,570,700,790,920,1030,1190]
    for x,t in zip(xs,headers): d.text((x,163),t,font=_font(16,True),fill=MUTED)
    y=220
    for r in records:
        d.rectangle((35,y,1465,y+52),fill=PANEL if (y//52)%2 else '#0d2840')
        pred=f"{r.get('home_goals','-')}-{r.get('away_goals','-')}"; actual=f"{r.get('actual_home','-')}-{r.get('actual_away','-')}"
        vals=[str(r.get('fixture',''))[:31],pred,actual,_ok(r.get('winner_correct')),_ok(r.get('ou25_correct')),_ok(r.get('btts_correct')),_ok(r.get('score_correct')),f"{int(r.get('points',0) or 0)}/40"]
        for i,(x,v) in enumerate(zip(xs,vals)):
            fill=(GREEN if v=='✓' else RED if v=='✕' else GOLD if i==7 else WHITE)
            d.text((x,y+15),v,font=_font(15, i in (0,7)),fill=fill)
        y+=58
    p,m,pct=_points(records)
    d.rounded_rectangle((35,y+20,1465,y+150),18,fill='#092b38',outline=BORDER,width=2)
    d.text((60,y+42),f'HAFTA GENELİ   {p}/{m} PUAN   %{pct:.1f}',font=_font(28,True),fill=BLUE)
    labels=[('Kazanan','winner_correct'),('Alt/Üst 2.5','ou25_correct'),('KG Var/Yok','btts_correct'),('Tam Skor','score_correct')]
    xx=60
    for label,key in labels:
        c,n,pc=_stats(records,key); d.text((xx,y+98),f'{label}: {c}/{n}  %{pc:.0f}',font=_font(16,True),fill=GREEN if pc>=50 else RED); xx+=340
    _signature(d,h); output=Path(output); output.parent.mkdir(parents=True,exist_ok=True); im.save(output,'PNG'); return output

def create_season_report(records, output:Path):
    im,d=_base('SEZON GENELİ AL PERFORMANSI','TOPLAM VERİ  •  GERÇEK SONUÇLAR  •  4 HAFTALIK GELİŞİM DÖNGÜSÜ',720)
    p,m,pct=_points(records)
    d.rounded_rectangle((45,150,1455,305),22,fill=PANEL,outline=BORDER,width=2)
    d.text((80,185),f'{p} / {m} PUAN',font=_font(42,True),fill=GOLD); d.text((80,245),f'Değerlendirilen maç: {len(records)}',font=_font(20),fill=MUTED)
    d.text((1120,185),f'%{pct:.1f}',font=_font(58,True),fill=BLUE)
    labels=[('KAZANAN (1X2)','winner_correct'),('ALT / ÜST 2.5','ou25_correct'),('KG VAR / YOK','btts_correct'),('TAM SKOR','score_correct')]
    for i,(label,key) in enumerate(labels):
        x=45+i*355; c,n,pc=_stats(records,key)
        d.rounded_rectangle((x,340,x+330,520),20,fill='#092b38',outline=GREEN if pc>=50 else RED,width=2)
        d.text((x+22,370),label,font=_font(18,True),fill=WHITE); d.text((x+22,420),f'{c}/{n}',font=_font(26,True),fill=MUTED); d.text((x+22,462),f'%{pc:.1f}',font=_font(36,True),fill=GREEN if pc>=50 else RED)
    d.text((55,565),'AL geliştirmesi: Her 4 haftalık gerçek tahmin dönemi tamamlandıktan sonra performans verisiyle değerlendirilir.',font=_font(17),fill=MUTED)
    _signature(d,720); output=Path(output); output.parent.mkdir(parents=True,exist_ok=True); im.save(output,'PNG'); return output
