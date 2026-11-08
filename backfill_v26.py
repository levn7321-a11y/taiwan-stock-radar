
import argparse
import logging
import re
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

import requests

DB = Path(__file__).resolve().parent / "twstock.sqlite3"
LOG = logging.getLogger("v26")

TWSE_PRICE = (
    "https://www.twse.com.tw/rwd/zh/"
    "afterTrading/MI_INDEX"
)
TWSE_INST = (
    "https://www.twse.com.tw/rwd/zh/fund/T86"
)
TPEX_PRICE = (
    "https://www.tpex.org.tw/web/stock/"
    "aftertrading/otc_quotes_no1430/"
    "stk_wn1430_result.php"
)
TPEX_INST = (
    "https://www.tpex.org.tw/web/stock/"
    "3insti/daily_trade/"
    "3itrade_hedge_result.php"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json,text/plain,*/*",
}

SESSION = requests.Session()
SESSION.headers.update(HEADERS)


def numeric(value):
    if value is None:
        return None
    s = re.sub(r"<[^>]+>", "", str(value))
    s = s.replace(",", "").replace("＋", "+")
    s = s.replace("−", "-").strip()
    if s in ("", "-", "--", "---", "—", "X"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def integer(value):
    v = numeric(value)
    return int(v) if v is not None else None


def fetch(url, params):
    for attempt in range(3):
        try:
            r = SESSION.get(
                url, params=params, timeout=30
            )
            r.raise_for_status()
            return r.json()
        except (requests.RequestException, ValueError) as e:
            LOG.warning(
                "請求失敗 %s 第%d次：%s",
                url, attempt + 1, e
            )
            time.sleep(3 * (attempt + 1))
    return None


def roc_day(day):
    return (
        f"{day.year - 1911}/"
        f"{day.month:02d}/{day.day:02d}"
    )


def code_ok(code):
    return bool(
        re.fullmatch(r"[0-9A-Za-z]{4,6}", str(code))
    )


def normalize_header(value):
    return re.sub(r"\s+", "", str(value))


def column(fields, patterns):
    normalized = [
        normalize_header(x) for x in fields
    ]
    for pattern in patterns:
        for i, name in enumerate(normalized):
            if pattern in name:
                return i
    return None


def init_db(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutional (
            date TEXT NOT NULL,
            market TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            foreign_net INTEGER,
            trust_net INTEGER,
            dealer_net INTEGER,
            PRIMARY KEY(date,market,code)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS v26_progress (
            dataset TEXT PRIMARY KEY,
            next_day TEXT NOT NULL
        )
    """)
    conn.commit()


def existing_price_columns(conn):
    row = conn.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type='table' AND name='daily'"
    ).fetchone()
    if not row:
        raise RuntimeError(
            "找不到 daily 資料表，"
            "請先使用原有系統建立行情資料庫"
        )
    return {
        r[1] for r in conn.execute(
            "PRAGMA table_info(daily)"
        )
    }


def save_prices(conn, records):
    cols = existing_price_columns(conn)
    required = {
        "date", "market", "code",
        "name", "close", "volume"
    }
    if not required.issubset(cols):
        raise RuntimeError(
            "daily 欄位與 V2.6 不相容，"
            "請檢查原有資料庫結構"
        )

    # 保留現有資料；僅新增缺少的歷史交易日。
    sql = """
        INSERT INTO daily
        (date,market,code,name,close,volume)
        SELECT ?,?,?,?,?,?
        WHERE NOT EXISTS (
            SELECT 1 FROM daily
            WHERE date=? AND market=? AND code=?
        )
    """

    for r in records:
        values = (
            r["date"], r["market"], r["code"],
            r["name"], r["close"], r["volume"]
        )
        conn.execute(
            sql,
            values + (
                r["date"], r["market"], r["code"]
            )
        )


def save_institutions(conn, records):
    conn.executemany("""
        INSERT INTO institutional
        (date,market,code,name,
         foreign_net,trust_net,dealer_net)
        VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(date,market,code)
        DO UPDATE SET
            name=excluded.name,
            foreign_net=excluded.foreign_net,
            trust_net=excluded.trust_net,
            dealer_net=excluded.dealer_net
    """, [
        (
            r["date"], r["market"],
            r["code"], r["name"],
            r["foreign_net"], r["trust_net"],
            r["dealer_net"]
        )
        for r in records
    ])


def parse_twse_prices(data, day):
    result = []
    if not isinstance(data, dict):
        return result

    for table in data.get("tables", []):
        fields = table.get("fields", [])
        rows = table.get("data", [])

        ci = column(fields, ["證券代號"])
        ni = column(fields, ["證券名稱"])
        vi = column(fields, ["成交股數"])
        pi = column(fields, ["收盤價"])

        if None in (ci, ni, vi, pi):
            continue

        for row in rows:
            try:
                code = str(row[ci]).strip()
                close = numeric(row[pi])
                volume = integer(row[vi])
                if not code_ok(code) or close is None:
                    continue
                result.append({
                    "date": day.isoformat(),
                    "market": "上市",
                    "code": code,
                    "name": str(row[ni]).strip(),
                    "close": close,
                    "volume": volume or 0,
                })
            except (IndexError, TypeError):
                continue

    return result


def parse_tpex_prices(data, day):
    result = []
    if not isinstance(data, dict):
        return result

    rows = data.get("aaData", [])
    if not rows:
        rows = data.get("data", [])

    for row in rows:
        try:
            # 舊版櫃買日行情：
            # 代號、名稱、收盤、漲跌、開盤、
            # 最高、最低、均價、成交股數...
            code = str(row[0]).strip()
            close = numeric(row[2])
            volume = integer(row[8])

            if not code_ok(code) or close is None:
                continue

            result.append({
                "date": day.isoformat(),
                "market": "上櫃",
                "code": code,
                "name": str(row[1]).strip(),
                "close": close,
                "volume": volume or 0,
            })
        except (IndexError, TypeError):
            continue

    return result


def parse_twse_institutions(data, day):
    result = []
    if not isinstance(data, dict):
        return result

    if data.get("stat") != "OK":
        return result

    fields = data.get("fields", [])
    rows = data.get("data", [])

    ci = column(fields, ["證券代號"])
    ni = column(fields, ["證券名稱"])
    fi = column(
        fields,
        ["外陸資買賣超股數(不含外資自營商)"]
    )
    ti = column(fields, ["投信買賣超股數"])
    di = column(fields, ["自營商買賣超股數"])

    if None in (ci, ni, fi, ti, di):
        LOG.warning("上市法人欄位格式改變")
        return result

    for row in rows:
        try:
            code = str(row[ci]).strip()
            if not code_ok(code):
                continue

            result.append({
                "date": day.isoformat(),
                "market": "上市",
                "code": code,
                "name": str(row[ni]).strip(),
                "foreign_net": integer(row[fi]),
                "trust_net": integer(row[ti]),
                "dealer_net": integer(row[di]),
            })
        except (IndexError, TypeError):
            continue

    return result


def parse_tpex_institutions(data, day):
    result = []
    if not isinstance(data, dict):
        return result

    rows = data.get("aaData", [])
    if not rows:
        rows = data.get("data", [])

    for row in rows:
        try:
            # 櫃買舊版三大法人每日交易表
            # 外資淨額、投信淨額、自營商淨額
            code = str(row[0]).strip()
            if not code_ok(code) or len(row) < 23:
                continue

            result.append({
                "date": day.isoformat(),
                "market": "上櫃",
                "code": code,
                "name": str(row[1]).strip(),
                "foreign_net": integer(row[10]),
                "trust_net": integer(row[13]),
                "dealer_net": integer(row[22]),
            })
        except (IndexError, TypeError):
            continue

    return result


def collect_day(conn, day, include_prices=True):
    ad = day.strftime("%Y%m%d")
    roc = roc_day(day)

    requests_to_make = []

    if include_prices:
        requests_to_make.extend([
            (
                TWSE_PRICE,
                {
                    "date": ad,
                    "type": "ALLBUT0999",
                    "response": "json"
                },
                parse_twse_prices,
                "price",
            ),
            (
                TPEX_PRICE,
                {
                    "l": "zh-tw",
                    "d": roc,
                    "se": "EW"
                },
                parse_tpex_prices,
                "price",
            ),
        ])

    requests_to_make.extend([
        (
            TWSE_INST,
            {
                "date": ad,
                "selectType": "ALLBUT0999",
                "response": "json"
            },
            parse_twse_institutions,
            "inst",
        ),
        (
            TPEX_INST,
            {
                "l": "zh-tw",
                "se": "EW",
                "t": "D",
                "d": roc
            },
            parse_tpex_institutions,
            "inst",
        ),
    ])

    total = 0

    for url, params, parser, kind in requests_to_make:
        payload = fetch(url, params)
        if payload is None:
            continue

        rows = parser(payload, day)
        if rows:
            if kind == "price":
                save_prices(conn, rows)
            else:
                save_institutions(conn, rows)
            conn.commit()
            total += len(rows)

        time.sleep(1.5)

    LOG.info("%s：取得 %s 筆", day, total)
    return total


def run(days_per_run, reset=False):
    today = date.today()

    # 450 日行情回補，法人取最近 365 日。
    oldest = today - timedelta(days=450)
    inst_oldest = today - timedelta(days=365)

    with sqlite3.connect(DB) as conn:
        init_db(conn)

        if reset:
            conn.execute(
                "DELETE FROM v26_progress "
                "WHERE dataset='history'"
            )
            conn.commit()

        row = conn.execute(
            "SELECT next_day FROM v26_progress "
            "WHERE dataset='history'"
        ).fetchone()

        cursor = (
            date.fromisoformat(row[0])
            if row else today
        )

        # 每次先更新最近幾天，處理資料延後公布。
        for offset in range(4):
            day = today - timedelta(days=offset)
            if day.weekday() < 5:
                collect_day(conn, day)

        # 歷史回補由近到遠，逐批完成。
        processed = 0

        while cursor >= oldest and processed < days_per_run:
            if cursor.weekday() < 5:
                # 365天以外只回補行情。
                include_inst = cursor >= inst_oldest

                if include_inst:
                    collect_day(conn, cursor)
                else:
                    # 只取得行情，不取法人
                    collect_price_day(conn, cursor)

            cursor -= timedelta(days=1)
            processed += 1

        conn.execute("""
            INSERT INTO v26_progress(dataset,next_day)
            VALUES('history',?)
            ON CONFLICT(dataset)
            DO UPDATE SET next_day=excluded.next_day
        """, (cursor.isoformat(),))
        conn.commit()

        if cursor < oldest:
            LOG.info("歷史回補日期範圍已完成")
        else:
            LOG.info(
                "本批完成，下一次從 %s 繼續",
                cursor
            )


def collect_price_day(conn, day):
    ad = day.strftime("%Y%m%d")
    roc = roc_day(day)

    sources = [
        (
            TWSE_PRICE,
            {
                "date": ad,
                "type": "ALLBUT0999",
                "response": "json"
            },
            parse_twse_prices,
        ),
        (
            TPEX_PRICE,
            {
                "l": "zh-tw",
                "d": roc,
                "se": "EW"
            },
            parse_tpex_prices,
        ),
    ]

    for url, params, parser in sources:
        payload = fetch(url, params)
        if payload is not None:
            rows = parser(payload, day)
            if rows:
                save_prices(conn, rows)
                conn.commit()
        time.sleep(1.5)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s"
    )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--days", type=int, default=30
    )
    parser.add_argument(
        "--reset", action="store_true"
    )
    args = parser.parse_args()

    run(
        days_per_run=max(1, min(args.days, 90)),
        reset=args.reset,
    )
