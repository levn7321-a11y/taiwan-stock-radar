"""Scheduled daily refresh, plus optional backfill. Run in repository root."""
import argparse
import datetime as dt
from zoneinfo import ZoneInfo
from history import backfill
from storage import init_db, save, fetch_latest

p=argparse.ArgumentParser()
p.add_argument('--backfill-days',type=int,default=0)
p.add_argument('--market',choices=['both','上市','上櫃'],default='both')
a=p.parse_args()
init_db()
today=dt.datetime.now(ZoneInfo('Asia/Taipei')).date()
if a.backfill_days:
    result=backfill(save,today-dt.timedelta(days=a.backfill_days),today,market=a.market)
    print(result)
    if result['errors']:raise SystemExit(f'{len(result["errors"])} requests failed; rerun for recovery')
else:
    results=fetch_latest()
    print(results)
    if results['errors']:raise SystemExit('Daily snapshot incomplete')
