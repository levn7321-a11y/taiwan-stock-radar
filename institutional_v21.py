"""TWSE/TPEX institutional flow collector; no scraping of third-party websites."""
from __future__ import annotations
import csv, io, json, re, time
from datetime import date, datetime, timedelta
from pathlib import Path
import requests

DATA_PATH = Path(__file__).resolve().parent / 'data' / 'institutional_daily.csv'
HEADERS = {'User-Agent':'Mozilla/5.0 (compatible; TaiwanStockRadar/2.1)', 'Accept':'application/json,text/plain,*/*'}
FIELDS = ['date','market','code','name','foreign_net_shares','trust_net_shares','foreign_net_lots','trust_net_lots']

def num(x):
    try: return int(float(str(x).replace(',','').replace('+','').strip()))
    except (ValueError,TypeError): return 0

def get_json(url, params):
    r=requests.get(url,params=params,headers=HEADERS,timeout=35)
    r.raise_for_status()
    return r.json()

def twse(day):
    payload=get_json('https://www.twse.com.tw/rwd/zh/fund/T86', {'date':day.strftime('%Y%m%d'),'selectType':'ALLBUT0999','response':'json'})
    rows=payload.get('data') or []
    fields=payload.get('fields') or []
    if not rows: return []
    # Locate columns by their published headings, not by unstable positions.
    def idx(parts):
        for i,s in enumerate(fields):
            normalized=re.sub(r'\s|<[^>]+>','',str(s))
            if all(p in normalized for p in parts): return i
        return None
    foreign=idx(['外陸資','買賣超'])
    if foreign is None: foreign=idx(['外資','買賣超'])
    trust=idx(['投信','買賣超'])
    if foreign is None or trust is None: raise ValueError('TWSE 欄位格式已變更：'+repr(fields))
    out=[]
    for r in rows:
        code=str(r[0]).strip()
        if not re.fullmatch(r'\d{4}',code): continue
        f,t=num(r[foreign]),num(r[trust])
        out.append(dict(date=day.isoformat(),market='上市',code=code,name=str(r[1]).strip(),foreign_net_shares=f,trust_net_shares=t,foreign_net_lots=round(f/1000,3),trust_net_lots=round(t/1000,3)))
    return out

def tpex(day):
    # TPEX public daily institutional trade JSON. Validate schema to avoid wrong rankings.
    payload=get_json('https://www.tpex.org.tw/www/zh-tw/3insti/daily_trade', {'date':day.strftime('%Y/%m/%d'),'response':'json'})
    tables=payload.get('tables') or []
    if not tables and payload.get('data'):
        tables=[payload]
    out=[]
    for table in tables:
        fields=table.get('fields') or table.get('header') or []
        rows=table.get('data') or []
        if not fields or not rows: continue
        cleaned=[re.sub(r'\s|<[^>]+>','',str(x)) for x in fields]
        def locate(keywords):
            return next((i for i,h in enumerate(cleaned) if all(k in h for k in keywords)),None)
        ci=locate(['代號']); ni=locate(['名稱'])
        fi=locate(['外資','買賣超']); ti=locate(['投信','買賣超'])
        if fi is None: fi=locate(['外陸資','買賣超'])
        if None in (ci,ni,fi,ti): continue
        for r in rows:
            code=str(r[ci]).strip()
            if not re.fullmatch(r'\d{4}',code): continue
            f,t=num(r[fi]),num(r[ti])
            out.append(dict(date=day.isoformat(),market='上櫃',code=code,name=str(r[ni]).strip(),foreign_net_shares=f,trust_net_shares=t,foreign_net_lots=round(f/1000,3),trust_net_lots=round(t/1000,3)))
    if not out: raise ValueError('TPEX 無可辨識的法人資料欄位，請檢查官方回應格式')
    return out

def update(days=7):
    DATA_PATH.parent.mkdir(parents=True,exist_ok=True)
    existing={}
    if DATA_PATH.exists():
        with DATA_PATH.open(encoding='utf-8-sig',newline='') as f:
            for r in csv.DictReader(f): existing[(r['date'],r['market'],r['code'])]=r
    errors=[]; added=0
    today=date.today()
    for offset in range(max(1,days)):
        d=today-timedelta(days=offset)
        if d.weekday()>=5: continue
        for market,fetch in [('上市',twse),('上櫃',tpex)]:
            try:
                records=fetch(d)
                for r in records: existing[(r['date'],r['market'],r['code'])]=r
                added+=len(records)
            except Exception as exc:
                errors.append(f'{d} {market}: {exc}')
        time.sleep(.25)
    with DATA_PATH.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(sorted(existing.values(),key=lambda r:(r['date'],r['market'],r['code'])))
    print(json.dumps({'records_fetched':added,'total_rows':len(existing),'errors':errors},ensure_ascii=False,indent=2))
    if added==0: raise RuntimeError('未取得任何法人資料；檢查網路、官方資料發布時間與 API 欄位')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--days',type=int,default=7);args=p.parse_args()
    update(args.days)
