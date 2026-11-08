"""回補 MA240 所需真實日行情：只抓上市／上櫃近 370 天尚缺的完整 OHLCV 日期。

不人工補值、不修改法人紀錄。API 空值／非交易日不寫入；
中斷後重新執行會跳過已完整入庫的日期。
"""
import argparse
import datetime as dt
import sqlite3
import time
from zoneinfo import ZoneInfo

import pandas as pd

from history import fetch_day
from storage import DB, init_db, save


def missing_jobs(conn, start, end, minimum_by_market=None):
    minimum_by_market = minimum_by_market or {"上市": 500, "上櫃": 250}
    existing = {
        (row[0], row[1]): row[2]
        for row in conn.execute(
            "SELECT date,market,COUNT(*) FROM daily GROUP BY date,market"
        )
    }
    result = []
    for stamp in pd.bdate_range(start, end):
        day = stamp.date()
        for market in ("上市", "上櫃"):
            if existing.get((day.isoformat(), market), 0) < minimum_by_market[market]:
                result.append((day, market))
    return result


def run(days=370, pause=0.25):
    if not 1 <= days <= 370:
        raise ValueError("回補天數限制 1～370 日曆天")
    init_db()
    today = dt.datetime.now(ZoneInfo("Asia/Taipei")).date()
    start = today - dt.timedelta(days=days)
    with sqlite3.connect(DB) as conn:
        jobs = missing_jobs(conn, start, today)
    print(f"MA240 回補：{start} 至 {today}，待抓 {len(jobs)} 個市場交易日組合", flush=True)
    saved_dates = 0
    failures = []
    for n, (day, market) in enumerate(jobs, start=1):
        try:
            data = fetch_day(day, market)
            if data.empty:
                print(f"[{n}/{len(jobs)}] {day} {market}: 無交易資料", flush=True)
            else:
                save(data)
                saved_dates += 1
                print(f"[{n}/{len(jobs)}] {day} {market}: 寫入 {len(data)} 筆", flush=True)
        except Exception as exc:
            failures.append(f"{day} {market}: {str(exc)[:180]}")
            print(f"[{n}/{len(jobs)}] 警告：{failures[-1]}", flush=True)
        if pause:
            time.sleep(pause)
    with sqlite3.connect(DB) as conn:
        count = conn.execute(
            """SELECT COUNT(*) FROM (
                SELECT market,code FROM daily
                GROUP BY market,code HAVING COUNT(DISTINCT date)>=240
            )"""
        ).fetchone()[0]
        sample = conn.execute(
            "SELECT market,code,COUNT(DISTINCT date) FROM daily WHERE code IN ('2330','2317') GROUP BY market,code"
        ).fetchall()
    print(f"本次新增市場日={saved_dates}；符合 MA240 最低日數股票={count}；樣本={sample}",flush=True)
    for issue in failures[:25]:
        print("失敗：" + issue,flush=True)
    # 有部分官方抓取錯誤仍保存已取得資料；待下次重跑補缺。
    return saved_dates, failures


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=370)
    parser.add_argument("--pause", type=float, default=0.25)
    args = parser.parse_args()
    run(args.days, args.pause)
