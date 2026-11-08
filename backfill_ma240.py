"""以官方實際歷史行情逐批回補至每個市場至少 260 個交易日。

不模擬缺漏行情，也不強制填入 MA240。新上市或停牌個股仍須逐檔核對。
每次執行上限 3 批，每批最多 90 個日曆日；進度保存於 SQLite。
"""
import argparse
import logging
import sqlite3

from backfill_v26 import DB, init_db, run

LOG = logging.getLogger("ma240_backfill")


def market_sessions(path=DB):
    with sqlite3.connect(path) as conn:
        init_db(conn)
        data = conn.execute("""
            SELECT market, COUNT(DISTINCT date)
            FROM daily
            WHERE market IN ('上市', '上櫃') AND close > 0
            GROUP BY market
        """).fetchall()
    return {market: int(count) for market, count in data}


def backfill_until(target=260, batches=3, calendar_days=90):
    before = market_sessions()
    LOG.warning("目前已知交易日：%s", before)
    for index in range(1, batches + 1):
        if all(before.get(market, 0) >= target for market in ("上市", "上櫃")):
            LOG.warning("兩市場已有至少 %d 個交易日，停止歷史補齊", target)
            break
        LOG.warning("進行歷史補齊第 %d/%d 批，處理 %d 個日曆日",
                    index, batches, calendar_days)
        run(days=calendar_days, reset=False)
        after = market_sessions()
        LOG.warning("第 %d 批完成，交易日 %s -> %s", index, before, after)
        before = after
    if not all(before.get(market, 0) >= target for market in ("上市", "上櫃")):
        LOG.warning("仍未達到 %d 個交易日；將由下次排程從進度繼續回補。", target)
    else:
        LOG.warning("已達歷史交易日目標：%s。個股需滿240筆才能產生MA240。", before)
    return before


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=int, default=260)
    parser.add_argument("--batches", type=int, default=3)
    parser.add_argument("--days", type=int, default=90)
    args = parser.parse_args()
    backfill_until(target=max(240, args.target),
                   batches=max(1, min(args.batches, 3)),
                   calendar_days=max(1, min(args.days, 90)))
