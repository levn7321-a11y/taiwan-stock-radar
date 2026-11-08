
# 台股 AI 突破雷達 V2.6.1
# 上市／上櫃行情與三大法人歷史回補
# 使用方式：
# python backfill_v26.py --days 10
# python backfill_v26.py --days 30
# 注意：請勿隨意使用 --reset

import argparse
import logging
import re
import sqlite3
import time
from datetime import date, timedelta
from pathlib import Path

import requests

DB = Path(__file__).resolve().parent / "twstock.sqlite3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger("V2.6.1")

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, */*"
})

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
    "https://www.tpex.org.tw/www/zh-tw/"
    "insti/dailyTrade"
)


def number(value):
    if value is None:
        return None
    s = re.sub(r"<[^>]*>", "", str(value))
    s = s.replace(",", "").replace("−", "-").strip()
    if s in ("", "-", "--", "---", "—", "X"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def integer(value):
    n = number(value)
    return int(n) if n is not None else None


def valid_code(value):
    return bool(
        re.fullmatch(r"[0-9A-Za-z]{4,6}", str(value))
    )


def roc_date(day):
    return (
        f"{day.year - 1911}/"
        f"{day.month:02d}/{day.day:02d}"
    )


def normalize_field(value):
    return re.sub(
        r"[\s（）()＋+]",
        "",
        str(value)
    )


def field_index(fields, keywords):
    normalized = [
        normalize_field(x) for x in fields
    ]
    for keyword in keywords:
        key = normalize_field(keyword)
        for i, name in enumerate(normalized):
            if key in name:
                return i
    return None


def get_json(url, params):
    for attempt in range(3):
        try:
            r = session.get(
                url,
                params=params,
                timeout=40
            )
            r.raise_for_status()
            return r.json()
        except Exception as exc:
            log.warning(
                "API 第 %d 次失敗：%s",
                attempt + 1, exc
            )
            time.sleep(3 * (attempt + 1))
    return None


def ensure_database(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutional (
            date TEXT NOT NULL,
            market TEXT NOT NULL,
            code TEXT NOT NULL,
            name TEXT,
            foreign_net INTEGER,
            trust_net INTEGER,
            dealer_net INTEGER,
            PRIMARY KEY(date, market, code)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS v26_progress (
            dataset TEXT PRIMARY KEY,
            next_day TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS v26_retry_dates (
            date TEXT PRIMARY KEY
        )
    """)

    conn.commit()


def parse_twse_prices(data, day):
    result = []
    if not isinstance(data, dict):
        return result

    for table in data.get("tables", []):
        fields = table.get("fields", [])
        rows = table.get("data", [])

        ci = field_index(fields, ["證券代號"])
        ni = field_index(fields, ["證券名稱"])
        pi = field_index(fields, ["收盤價"])
        vi = field_index(fields, ["成交股數"])

        if None in (ci, ni, pi, vi):
            continue

        for row in rows:
            try:
                code = str(row[ci]).strip()
                close = number(row[pi])
                volume = integer(row[vi])

                if not valid_code(code):
                    continue
                if close is None or volume is None:
                    continue

                result.append((
                    day.isoformat(), "上市", code,
                    str(row[ni]).strip(),
                    close, volume
                ))
            except (IndexError, TypeError):
                continue

    return result


def parse_tpex_prices(data, day):
    result = []
    if not isinstance(data, dict):
        return result

    rows = data.get("aaData") or data.get("data") or []

    for row in rows:
        try:
            code = str(row[0]).strip()
            close = number(row[2])
            volume = integer(row[8])

            if not valid_code(code):
                continue
            if close is None or volume is None:
                continue

            result.append((
                day.isoformat(), "上櫃", code,
                str(row[1]).strip(),
                close, volume
            ))
        except (IndexError, TypeError):
            continue

    return result


def parse_twse_institutions(data, day):
    result = []
    if not isinstance(data, dict):
        return result

    fields = data.get("fields", [])
    rows = data.get("data", [])

    ci = field_index(fields, ["證券代號"])
    ni = field_index(fields, ["證券名稱"])
    fi = field_index(fields, [
        "外陸資買賣超股數不含外資自營商"
    ])
    ti = field_index(fields, [
        "投信買賣超股數"
    ])
    di = field_index(fields, [
        "自營商買賣超股數"
    ])

    if None in (ci, ni, fi, ti, di):
        log.error("上市法人欄位不符：%s", fields)
        return result

    for row in rows:
        try:
            code = str(row[ci]).strip()
            if not valid_code(code):
                continue

            foreign = integer(row[fi])
            trust = integer(row[ti])
            dealer = integer(row[di])

            if None in (foreign, trust, dealer):
                continue

            result.append((
                day.isoformat(), "上市", code,
                str(row[ni]).strip(),
                foreign, trust, dealer
            ))
        except (IndexError, TypeError):
            continue

    return result


def tpex_table_rows(data):
    """取得櫃買中心資料表及欄位名稱。"""
    if not isinstance(data, dict):
        return [], []

    tables = data.get("tables", [])
    if isinstance(tables, list):
        for table in tables:
            if not isinstance(table, dict):
                continue
            fields = table.get("fields", [])
            rows = table.get("data", [])
            if fields and rows:
                return fields, rows

    fields = (
        data.get("fields")
        or data.get("columnNames")
        or []
    )
    rows = (
        data.get("data")
        or data.get("aaData")
        or []
    )
    return fields, rows


def parse_tpex_institutions(data, day):
    """
    上櫃法人資料：
    只依照 API 回傳的欄位名稱取值。
    無法確認欄位時不寫入，避免錯誤籌碼。
    """
    result = []
    fields, rows = tpex_table_rows(data)

    if not fields:
        log.error(
            "%s 上櫃法人缺少欄位名稱；"
            "資料鍵值：%s",
            day,
            list(data.keys()) if isinstance(data, dict)
            else "非 JSON 物件"
        )
        return result

    ci = field_index(fields, [
        "證券代號", "股票代號", "代號"
    ])
    ni = field_index(fields, [
        "證券名稱", "股票名稱", "名稱"
    ])
    fi = field_index(fields, [
        "外資及陸資不含外資自營商買賣超",
        "外資及陸資買賣超",
        "外資買賣超"
    ])
    ti = field_index(fields, [
        "投信買賣超"
    ])
    di = field_index(fields, [
        "自營商買賣超合計",
        "自營商合計買賣超",
        "自營商買賣超"
    ])

    if None in (ci, ni, fi, ti, di):
        log.error(
            "%s 上櫃法人欄位無法對應：%s",
            day, fields
        )
        return result

    invalid = 0

    for row in rows:
        try:
            code = str(row[ci]).strip()
            if not valid_code(code):
                continue

            foreign = integer(row[fi])
            trust = integer(row[ti])
            dealer = integer(row[di])

            if None in (foreign, trust, dealer):
                invalid += 1
                continue

            result.append((
                day.isoformat(), "上櫃", code,
                str(row[ni]).strip(),
                foreign, trust, dealer
            ))
        except (IndexError, TypeError):
            invalid += 1

    if invalid:
        log.error(
            "%s 上櫃法人 %d 筆解析失敗，"
            "本日不寫入",
            day, invalid
        )
        return []

    return result


def save_prices(conn, records):
    # 保留既有行情資料；新資料只補缺漏
    for row in records:
        conn.execute("""
            INSERT INTO daily
            (date, market, code, name, close, volume)
            SELECT ?, ?, ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1 FROM daily
                WHERE date = ?
                  AND market = ?
                  AND code = ?
            )
        """, row + row[:3])


def save_institutions(conn, records):
    # 同一天同市場的資料重新寫入，
    # 避免舊版錯誤數字殘留。
    day, market = records[0][:2]

    conn.execute("""
        DELETE FROM institutional
        WHERE date = ? AND market = ?
    """, (day, market))

    conn.executemany("""
        INSERT INTO institutional
        (date, market, code, name,
         foreign_net, trust_net, dealer_net)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, records)


def process_source(
    conn, day, market, kind,
    url, params, parser
):
    data = get_json(url, params)

    if data is None:
        log.error(
            "%s %s %s：API 失敗",
            day, market, kind
        )
        return False

    records = parser(data, day)

    if not records:
        log.warning(
            "%s %s %s：取得 0 筆",
            day, market, kind
        )
        return False

    try:
        with conn:
            if kind == "行情":
                save_prices(conn, records)
            else:
                save_institutions(conn, records)

        log.info(
            "%s %s %s：取得 %d 筆",
            day, market, kind, len(records)
        )
        return True
    except sqlite3.Error as exc:
        log.error(
            "%s %s %s：資料庫錯誤 %s",
            day, market, kind, exc
        )
        return False


def collect_day(conn, day, prices=True, inst=True):
    ad = day.strftime("%Y%m%d")
    roc = roc_date(day)
    tasks = []

    if prices:
        tasks.extend([
            (
                "上市", "行情", TWSE_PRICE,
                {
                    "date": ad,
                    "type": "ALLBUT0999",
                    "response": "json"
                },
                parse_twse_prices
            ),
            (
                "上櫃", "行情", TPEX_PRICE,
                {
                    "l": "zh-tw",
                    "d": roc,
                    "se": "EW"
                },
                parse_tpex_prices
            )
        ])

    if inst:
        tasks.extend([
            (
                "上市", "法人", TWSE_INST,
                {
                    "date": ad,
                    "selectType": "ALLBUT0999",
                    "response": "json"
                },
                parse_twse_institutions
            ),
            (
                "上櫃", "法人", TPEX_INST,
                {
                    "type": "Daily",
                    "sect": "EW",
                    "date": roc,
                    "id": "",
                    "response": "json"
                },
                parse_tpex_institutions
            )
        ])

    results = []

    for market, kind, url, params, parser in tasks:
        ok = process_source(
            conn, day, market, kind,
            url, params, parser
        )
        results.append(ok)
        time.sleep(1)

    return all(results) if results else True


def run(days, reset=False):
    today = date.today()
    oldest_price = today - timedelta(days=450)
    oldest_inst = today - timedelta(days=365)

    with sqlite3.connect(DB) as conn:
        ensure_database(conn)

        if reset:
            conn.execute("""
                DELETE FROM v26_progress
                WHERE dataset = 'history'
            """)
            conn.commit()

        row = conn.execute("""
            SELECT next_day
            FROM v26_progress
            WHERE dataset = 'history'
        """).fetchone()

        cursor = (
            date.fromisoformat(row[0])
            if row else today
        )

        # 先修補最近10天法人
        log.info("開始檢查最近10天法人資料")

        for offset in range(10):
            day = today - timedelta(days=offset)
            if day.weekday() >= 5:
                continue

            complete = collect_day(
                conn, day,
                prices=False, inst=True
            )
            if not complete:
                conn.execute("""
                    INSERT OR IGNORE
                    INTO v26_retry_dates(date)
                    VALUES (?)
                """, (day.isoformat(),))
                conn.commit()

        # 更新最近4天行情
        for offset in range(4):
            day = today - timedelta(days=offset)
            if day.weekday() >= 5:
                continue

            collect_day(
                conn, day,
                prices=True, inst=False
            )

        processed = 0
        failures = 0

        while (
            cursor >= oldest_price
            and processed < days
        ):
            day = cursor

            if day.weekday() < 5:
                ok = collect_day(
                    conn,
                    day,
                    prices=True,
                    inst=(day >= oldest_inst)
                )

                if not ok:
                    failures += 1
                    conn.execute("""
                        INSERT OR IGNORE
                        INTO v26_retry_dates(date)
                        VALUES (?)
                    """, (day.isoformat(),))
                    conn.commit()

            cursor -= timedelta(days=1)
            processed += 1

        conn.execute("""
            INSERT INTO v26_progress
            (dataset, next_day)
            VALUES ('history', ?)
            ON CONFLICT(dataset)
            DO UPDATE SET
                next_day = excluded.next_day
        """, (cursor.isoformat(),))

        conn.commit()

        log.info(
            "本批完成，下一次從 %s 繼續",
            cursor
        )
        log.info(
            "本批不完整日期數：%d",
            failures
        )
        log.info(
            "注意：待補日期已記錄，"
            "尚未實作自動重新處理待補清單"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--days", type=int, default=10
    )
    parser.add_argument(
        "--reset", action="store_true"
    )
    args = parser.parse_args()

    run(
        days=max(1, min(args.days, 90)),
        reset=args.reset
    )
