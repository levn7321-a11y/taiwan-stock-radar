"""Official TWSE/TPEx dated whole-market backfill. Errors are never silently accepted."""
import datetime as dt
import re
import time
import requests
import pandas as pd

FIELDS=['date','market','code','name','open','high','low','close','volume']
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; TWBreakoutResearch/2.0)','Accept':'application/json'}


def num(v):
    s=str(v if v is not None else '').strip().replace(',','').replace('+','')
    if s in ('','--','-','－','nan','None','除權息'):return None
    try:return float(s)
    except ValueError:return None


def day(v):
    s=str(v).strip().replace('/','').replace('-','')
    if s.isdigit() and len(s)==7:return f'{int(s[:3])+1911:04d}-{s[3:5]}-{s[5:7]}'
    if s.isdigit() and len(s)==8:return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    raise ValueError('unrecognized date '+str(v))


def get_json(url, params, session=None):
    client=session or requests
    r=client.get(url,params=params,headers=HEADERS,timeout=40)
    r.raise_for_status()
    return r.json()


def twse_parse(payload, requested):
    if not isinstance(payload,dict):raise ValueError('TWSE response not object')
    tables=payload.get('tables',[])
    if not isinstance(tables,list):raise ValueError('TWSE tables malformed')
    selected=None
    for table in tables:
        fields=[str(x).strip() for x in table.get('fields',[])]
        if all(any(token in f for f in fields) for token in ['證券代號','證券名稱','成交股數','開盤價','最高價','最低價','收盤價']):
            selected=table;break
    if selected is None:
        # Empty responses for holidays are fine, but changed schema on a trading day must be surfaced.
        if payload.get('stat') not in ('OK','ok'):return pd.DataFrame(columns=FIELDS)
        raise ValueError('TWSE missing expected stock price table')
    fs=[str(x).strip() for x in selected['fields']]
    def idx(term):return next(i for i,f in enumerate(fs) if term in f)
    rows=[]
    for r in selected.get('data',[]):
        try:
            code=str(r[idx('證券代號')]).strip()
            if not re.fullmatch(r'\d{4}',code):continue
            values=[num(r[idx(k)]) for k in ('開盤價','最高價','最低價','收盤價','成交股數')]
            if any(v is None for v in values) or values[3]<=0 or values[4]<0:continue
            rows.append((requested,'上市',code,str(r[idx('證券名稱')]).strip(),*values))
        except (IndexError,TypeError):continue
    return pd.DataFrame(rows,columns=FIELDS)


def tpex_parse(payload, requested):
    if not isinstance(payload,dict):raise ValueError('TPEx response not object')
    if payload.get('stat') not in (None,'ok','OK') and not payload.get('tables') and not payload.get('aaData'):
        return pd.DataFrame(columns=FIELDS)
    tables=payload.get('tables') or [payload]
    rows=[]
    for table in tables:
        fs=table.get('fields') or table.get('columnNames') or table.get('titles') or []
        data=table.get('data') or table.get('aaData') or []
        if data and isinstance(data[0],dict):
            fs=list(data[0].keys());data=[[r.get(k) for k in fs] for r in data]
        fs=[re.sub(r'<[^>]*>','',str(f)).strip() for f in fs]
        def col(*names):
            for n in names:
                for i,f in enumerate(fs):
                    if n in f:return i
            return None
        indices=[col('代號','股票代號','證券代號'),col('名稱','股票名稱','證券名稱'),col('開盤'),col('最高'),col('最低'),col('收盤'),col('成交股數','成交量')]
        if any(i is None for i in indices):continue
        for r in data:
            try:
                code=str(r[indices[0]]).strip()
                if not re.fullmatch(r'\d{4}',code):continue
                vals=[num(r[i]) for i in indices[2:]]
                if any(v is None for v in vals) or vals[3]<=0 or vals[4]<0:continue
                # Some TPEx endpoints report shares in thousands; only accept explicitly labeled units.
                unit=fs[indices[-1]]
                if '仟股' in unit or '千股' in unit:vals[-1]*=1000
                rows.append((requested,'上櫃',code,str(r[indices[1]]).strip(),*vals))
            except (IndexError,TypeError):continue
    if not rows and payload.get('stat') in ('ok','OK') and any((t.get('data') or t.get('aaData')) for t in tables):
        raise ValueError('TPEx historical schema mismatch; inspect fields before importing')
    return pd.DataFrame(rows,columns=FIELDS)


def fetch_day(date,market,session=None):
    d=date.strftime('%Y-%m-%d')
    if market=='上市':
        p=get_json('https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX',{'response':'json','date':date.strftime('%Y%m%d'),'type':'ALLBUT0999'},session)
        return twse_parse(p,d)
    p=get_json('https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes',{'response':'json','date':date.strftime('%Y/%m/%d')},session)
    return tpex_parse(p,d)


def backfill(save_fn,start,end,market='both',delay=0.5,progress=None):
    if (end-start).days>370:raise ValueError('Maximum 370 calendar days per run')
    markets=['上市','上櫃'] if market=='both' else [market]
    result={'saved':0,'days':0,'errors':[],'empty':0}
    dates=pd.date_range(start,end,freq='B')
    for d in dates:
        for m in markets:
            try:
                df=fetch_day(d.date(),m)
                if len(df):save_fn(df);result['saved']+=len(df);result['days']+=1
                else:result['empty']+=1
            except Exception as exc:
                result['errors'].append(f'{d.date()} {m}: {str(exc)[:150]}')
            if progress:progress(d.date(),m,result)
            if delay:time.sleep(delay)
    return result
