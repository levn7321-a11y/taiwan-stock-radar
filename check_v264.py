
# 台股 AI 突破雷達 V2.6.4
# 資料庫健康檢查：唯讀，不修改任何資料

import sqlite3
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

DB = Path(__file__).resolve().parent / "twstock.sqlite3"

# 依臺灣證券交易所 2026 年開休市行事曆
HOLIDAYS_2026 = {
    "2026-01-01",
    "2026-02-12",
    "2026-02-13",
    "2026-02-16",
    "2026-02-17",
    "2026-02-18",
    "2026-02-19",
    "2026-02-20",
    "2026-02-27",
    "2026-04-03",
    "2026-04-06",
    "2026-05-01",
    "2026-06-19",
    "2026-09-25",
    "2026-09-28",
    "2026-10-09",
    "2026-10-26",
    "2026-12-25",
}


def trading_day(day):
    if day.weekday() >= 5:
        return False
    if day.year == 2026:
        return day.isoformat() not in HOLIDAYS_2026
    return None  # 其他年份尚未載入正式行事曆


def table_exists(conn, name):
    return conn.execute(
        "SELECT 1 FROM sqlite_master "
        "WHERE type='table' AND name=?",
        (name,),
    ).fetchone() is not None


def report_table(conn, table):
    print(f"\n=== {table} 資料統計 ===")

    if not table_exists(conn, table):
        print("資料表不存在")
        return

    for market in ("上市", "上櫃"):
        row = conn.execute(
            f"""
            SELECT COUNT(*), COUNT(DISTINCT date),
                   MIN(date), MAX(date)
            FROM {table}
            WHERE market=?
            """,
            (market,),
        ).fetchone()

        print(
            f"{market}：{row[0]:,} 筆，"
            f"{row[1]} 個日期，"
            f"{row[2]} ~ {row[3]}"
        )


def report_missing(conn, table, start, end):
    print(f"\n=== {table} 交易日缺口 ===")

    if not table_exists(conn, table):
        print("資料表不存在")
        return

    for market in ("上市", "上櫃"):
        existing = {
            row[0]
            for row in conn.execute(
                f"""
                SELECT DISTINCT date
                FROM {table}
                WHERE market=? AND date BETWEEN ? AND ?
                """,
                (market, start.isoformat(), end.isoformat()),
            )
        }

        missing = []
        unknown = []
        day = start

        while day <= end:
            status = trading_day(day)

            if status is True and day.isoformat() not in existing:
                missing.append(day.isoformat())
            elif status is None:
                unknown.append(day.isoformat())

            day += timedelta(days=1)

        print(f"{market}：缺少 {len(missing)} 個已確認交易日")

        if missing:
            print("缺口日期：", ", ".join(missing[:30]))

        if unknown:
            print(
                f"另有 {len(unknown)} 個其他年份日期"
                "尚未核對休市行事曆"
            )


def report_retry(conn):
    print("\n=== 待重試任務 ===")

    if not table_exists(conn, "v26_retry_tasks"):
        print("尚無重試資料表")
        return

    rows = conn.execute(
        """
        SELECT date, market, kind
        FROM v26_retry_tasks
        ORDER BY date DESC
        """
    ).fetchall()

    holidays = []
    failures = []
    unknown = []

    for day_text, market, kind in rows:
        status = trading_day(date.fromisoformat(day_text))
        item = (day_text, market, kind)

        if status is False:
            holidays.append(item)
        elif status is True:
            failures.append(item)
        else:
            unknown.append(item)

    print(f"休市日造成的待重試：{len(holidays)}")
    print(f"正常交易日待重試：{len(failures)}")
    print(f"未確認行事曆：{len(unknown)}")

    for item in failures[:20]:
        print("需要補抓：", *item)

    # 本程式只列出，不刪除重試紀錄


def report_ma240(conn):
    print("\n=== MA240 年線資料檢查 ===")

    if not table_exists(conn, "daily"):
        print("daily 資料表不存在")
        return

    for market in ("上市", "上櫃"):
        rows = conn.execute(
            """
            SELECT code, COUNT(DISTINCT date)
            FROM daily
            WHERE market=? AND close IS NOT NULL
            GROUP BY code
            """,
            (market,),
        ).fetchall()

        ready = sum(count >= 240 for _, count in rows)

        print(
            f"{market}：{len(rows)} 檔股票，"
            f"{ready} 檔具備至少 240 日收盤資料，"
            f"{len(rows) - ready} 檔不足"
        )


def main():
    if not DB.exists():
        print("找不到資料庫：", DB)
        return

    conn = sqlite3.connect(
        f"file:{DB.as_posix()}?mode=ro",
        uri=True,
    )

    try:
        print("台股 AI 突破雷達 V2.6.4 健康檢查")
        print("資料庫：", DB.name)

        report_table(conn, "daily")
        report_table(conn, "institutional")

        # 先檢查已回補過的近期區間
        start = date(2026, 10, 1)
        end = min(date.today(), date(2026, 11, 6))

        report_missing(conn, "daily", start, end)
        report_missing(conn, "institutional", start, end)

        report_retry(conn)
        report_ma240(conn)

        print("\n檢查完成，未修改資料庫")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
