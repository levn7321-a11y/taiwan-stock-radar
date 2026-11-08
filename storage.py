import sqlite3
from pathlib import Path
import requests
import pandas as pd
from history import FIELDS,day,num
DB=Path(__file__).with_name('twstock.sqlite3')
TWSE='https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL'
TPEX='https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes'

def init_db():
    with sqlite3.connect(DB) as c:
        c.execute('CREATE TABLE IF NOT EXISTS daily(date TEXT,market TEXT,code TEXT,name TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL,PRIMARY KEY(date,market,code))')
        c.execute('CREATE INDEX IF NOT EXISTS ix_daily_date ON daily(date)')

def save(df):
    if df.empty:return
    with sqlite3.connect(DB,timeout=30) as c:
        c.executemany('INSERT OR REPLACE INTO daily VALUES (?,?,?,?,?,?,?,?,?)',df[FIELDS].itertuples(index=False,name=None))

def load():
    with sqlite3.connect(DB) as c:return pd.read_sql_query('SELECT * FROM daily ORDER BY market,code,date',c)

def parse_latest(rows,market):
    if not isinstance(rows,list):raise ValueError('Expected array')
    out=[]
    for r in rows:
        code=str(r.get('Code') if market=='上市' else r.get('SecuritiesCompanyCode','')).strip()
        if len(code)!=4 or not code.isdigit():continue
        keys=['OpeningPrice','HighestPrice','LowestPrice','ClosingPrice','TradeVolume'] if market=='上市' else ['Open','High','Low','Close','TradingShares']
        vals=[num(r.get(k)) for k in keys]
        if any(v is None for v in vals) or vals[3]<=0 or vals[4]<0:continue
        try:d=day(r.get('Date'))
        except ValueError:continue
        out.append((d,market,code,str(r.get('Name') if market=='上市' else r.get('CompanyName','')).strip(),*vals))
    if not out:raise ValueError('No valid stock rows; check upstream schema')
    return pd.DataFrame(out,columns=FIELDS)

def fetch_latest():
    result={'saved':0,'markets':{},'errors':[]}
    for market,url in [('上市',TWSE),('上櫃',TPEX)]:
        try:
            r=requests.get(url,timeout=45,headers={'User-Agent':'Mozilla/5.0','Accept':'application/json'});r.raise_for_status()
            df=parse_latest(r.json(),market);save(df)
            result['saved']+=len(df);result['markets'][market]={'rows':len(df),'date':df.date.max()}
        except Exception as e:result['errors'].append(f'{market}: {e}')
    return result
