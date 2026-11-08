
# 台股 AI 突破雷達 V2.6.3
# 上市／上櫃行情與三大法人歷史回補
# 修正櫃買中心法人欄位解析
# 保留既有資料、歷史進度及失敗重試機制

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
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("V2.6.3")

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, */*",
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


# ==========================================
# 基礎工具
# ==========================================

def num(value):
    if value is None:
        return None

    value = re.sub(r"<[^>]+>", "", str(value))
    value = value.replace(",", "").replace("−", "-")
    value = value.strip()

    if value in ("", "-", "--", "---", "—", "X"):
        return None

    try:
        return float(value)
    except (ValueError, OverflowError):
        return None


def integer(value):
    value = num(value)
    return int(value) if value is not None else None


def code_ok(value):
    return bool(re.fullmatch(
        r"[0-9A-Za-z]{4,6}",
        str(value).strip(),
    ))


def roc(day):
    return (
        f"{day.year - 1911}/"
        f"{day.month:02d}/"
        f"{day.day:02d}"
    )


def normalized(value):
    return re.sub(
        r"[\s（）()＋+]",
        "",
        str(value),
    )


def field_index(fields, names):
    clean = [normalized(f) for f in fields]

    for name in names:
        target = normalized(name)

        for i, field in enumerate(clean):
            if target in field:
                return i

    return None


def request_json(url, params):
    for attempt in range(3):
        try:
            response = session.get(
                url,
                params=params,
                timeout=40,
            )
            response.raise_for_status()
            return response.json()

        except Exception as exc:
            log.warning(
                "API 失敗 %d/3：%s",
                attempt + 1,
                exc,
            )
            time.sleep(2 * (attempt + 1))

    return None


# ==========================================
# 資料庫
# ==========================================

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
        CREATE TABLE IF NOT EXISTS v26_retry_tasks (
            date TEXT NOT NULL,
            market TEXT NOT NULL,
            kind TEXT NOT NULL,
            reason TEXT,
            PRIMARY KEY(date, market, kind)
        )
    """)

    conn.commit()


# ==========================================
# 上市行情解析
# ==========================================

def parse_twse_price(data, day):
    result = []

    if not isinstance(data, dict):
        return result

    for table in data.get("tables", []):
        if not isinstance(table, dict):
            continue

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
                close = num(row[pi])
                volume = integer(row[vi])

                if not code_ok(code):
                    continue

                if close is None or volume is None:
                    continue

                result.append((
                    day.isoformat(),
                    "上市",
                    code,
                    str(row[ni]).strip(),
                    close,
                    volume,
                ))

            except (IndexError, TypeError):
                continue

    return result


# ==========================================
# 櫃買中心表格解析
# ==========================================

def tpex_table(data):
    if not isinstance(data, dict):
        return [], []

    tables = data.get("tables", [])

    if isinstance(tables, list):
        for table in tables:
            if not isinstance(table, dict):
                continue

            fields = table.get("fields", [])
            rows = table.get("data", [])

            if isinstance(rows, list) and rows:
                return fields, rows

    fields = (
        data.get("fields")
        or data.get("columnNames")
        or []
    )

    rows = (
        data.get("aaData")
        or data.get("data")
        or []
    )

    return fields, rows


# ==========================================
# 上櫃行情解析
# ==========================================

def parse_tpex_price(data, day):
    result = []
    fields, rows = tpex_table(data)

    if not rows:
        return result

    ci = field_index(fields, ["代號"])
    ni = field_index(fields, ["名稱"])
    pi = field_index(fields, ["收盤"])
    vi = field_index(fields, ["成交股數"])

    if None in (ci, ni, pi, vi):
        if not fields and len(rows[0]) >= 17:
            ci, ni, pi, vi = 0, 1, 2, 7
        else:
            log.error(
                "%s 上櫃行情欄位不符：%s",
                day,
                fields,
            )
            return []

    for row in rows:
        try:
            code = str(row[ci]).strip()
            close = num(row[pi])
            volume = integer(row[vi])

            if not code_ok(code):
                continue

            if close is None or volume is None:
                continue

            result.append((
                day.isoformat(),
                "上櫃",
                code,
                str(row[ni]).strip(),
                close,
                volume,
            ))

        except (IndexError, TypeError):
            continue

    return result


# ==========================================
# 上市三大法人解析
# ==========================================

def parse_twse_inst(data, day):
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
        log.error(
            "%s 上市法人欄位不符：%s",
            day,
            fields,
        )
        return []

    for row in rows:
        try:
            code = str(row[ci]).strip()

            if not code_ok(code):
                continue

            foreign = integer(row[fi])
            trust = integer(row[ti])
            dealer = integer(row[di])

            if None in (foreign, trust, dealer):
                continue

            result.append((
                day.isoformat(),
                "上市",
                code,
                str(row[ni]).strip(),
                foreign,
                trust,
                dealer,
            ))

        except (IndexError, TypeError):
            continue

    return result


# ==========================================
# 上櫃三大法人解析 V2.6.3
# ==========================================

def parse_tpex_inst(data, day):
    """
    已依櫃買中心實際 JSON 資料確認：

    row[0]  = 股票代號
    row[1]  = 股票名稱
    row[10] = 外資及陸資買賣超合計
    row[13] = 投信買賣超
    row[22] = 自營商買賣超合計
    row[23] = 三大法人買賣超合計

    注意：
    API fields 內有多組重複的買賣超欄位名稱，
    因此不能依同名欄位搜尋法人類別。

    只接受已確認的 24 欄資料結構，
    並檢查三大法人合計是否一致。
    """

    result = []
    fields, rows = tpex_table(data)

    if not isinstance(rows, list) or not rows:
        log.warning(
            "%s 上櫃法人無資料",
            day,
        )
        return []

    # 目前已確認的官方格式為 24 欄
    # 若未來 API 欄位變動，停止寫入以避免錯誤。
    if len(fields) != 24:
        log.error(
            "%s 上櫃法人欄位數異常：%d",
            day,
            len(fields),
        )
        return []

    if (
        normalized(fields[0]) != "代號"
        or normalized(fields[1]) != "名稱"
        or "買賣超" not in normalized(fields[10])
        or "買賣超" not in normalized(fields[13])
        or "買賣超" not in normalized(fields[22])
        or "三大法人買賣超" not in normalized(fields[23])
    ):
        log.error(
            "%s 上櫃法人欄位格式變動：%s",
            day,
            fields,
        )
        return []

    invalid_count = 0
    checked_count = 0

    for row in rows:
        if not isinstance(row, (list, tuple)):
            invalid_count += 1
            continue

        if len(row) != 24:
            invalid_count += 1
            continue

        try:
            code = str(row[0]).strip()

            if not code_ok(code):
                continue

            foreign = integer(row[10])
            trust = integer(row[13])
            dealer = integer(row[22])
            total = integer(row[23])

            if None in (
                foreign,
                trust,
                dealer,
                total,
            ):
                invalid_count += 1
                continue

            checked_count += 1

            # 核對官方三大法人合計
            if foreign + trust + dealer != total:
                invalid_count += 1
                log.warning(
                    "%s 上櫃 %s 法人合計不一致："
                    "外資=%s 投信=%s 自營商=%s 合計=%s",
                    day,
                    code,
                    foreign,
                    trust,
                    dealer,
                    total,
                )
                continue

            result.append((
                day.isoformat(),
                "上櫃",
                code,
                str(row[1]).strip(),
                foreign,
                trust,
                dealer,
            ))

        except (
            IndexError,
            TypeError,
            ValueError,
            OverflowError,
        ):
            invalid_count += 1
            continue

    log.info(
        "%s 上櫃法人解析：原始 %d 筆，"
        "有效 %d 筆，異常 %d 筆",
        day,
        len(rows),
        len(result),
        invalid_count,
    )

    # 若出現資料格式異常，不覆寫既有資料
    if invalid_count > 0:
        log.error(
            "%s 上櫃法人存在異常資料，"
            "本日不寫入，保留重試",
            day,
        )
        return []

    if checked_count == 0:
        return []

    return result


# ==========================================
# 儲存行情
# ==========================================

def save_price(conn, records):
    for row in records:
        conn.execute("""
            INSERT INTO daily
            (date, market, code, name, close, volume)
            SELECT ?, ?, ?, ?, ?, ?
            WHERE NOT EXISTS (
                SELECT 1
                FROM daily
                WHERE date = ?
                  AND market = ?
                  AND code = ?
            )
        """, row + row[:3])


# ==========================================
# 儲存法人
# ==========================================

def save_inst(conn, records):
    if not records:
        return

    day, market = records[0][:2]

    conn.execute("""
        DELETE FROM institutional
        WHERE date = ?
          AND market = ?
    """, (day, market))

    conn.executemany("""
        INSERT INTO institutional
        (
            date,
            market,
            code,
            name,
            foreign_net,
            trust_net,
            dealer_net
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, records)


# ==========================================
# API 任務設定
# ==========================================

def task_config(day, market, kind):
    ad = day.strftime("%Y%m%d")
    rd = roc(day)

    if market == "上市" and kind == "行情":
        return (
            TWSE_PRICE,
            {
                "date": ad,
                "type": "ALLBUT0999",
                "response": "json",
            },
            parse_twse_price,
        )

    if market == "上櫃" and kind == "行情":
        return (
            TPEX_PRICE,
            {
                "l": "zh-tw",
                "d": rd,
                "se": "EW",
            },
            parse_tpex_price,
        )

    if market == "上市" and kind == "法人":
        return (
            TWSE_INST,
            {
                "date": ad,
                "selectType": "ALLBUT0999",
                "response": "json",
            },
            parse_twse_inst,
        )

    if market == "上櫃" and kind == "法人":
        return (
            TPEX_INST,
            {
                "type": "Daily",
                "sect": "EW",
                "date": rd,
                "id": "",
                "response": "json",
            },
            parse_tpex_inst,
        )

    raise ValueError(
        f"未知任務：{market} {kind}"
    )


# ==========================================
# 執行單一任務
# ==========================================

def run_task(conn, day, market, kind):
    url, params, parser = task_config(
        day,
        market,
        kind,
    )

    data = request_json(url, params)

    records = (
        parser(data, day)
        if data is not None
        else []
    )

    if records:
        try:
            with conn:
                if kind == "行情":
                    save_price(conn, records)
                else:
                    save_inst(conn, records)

                conn.execute("""
                    DELETE FROM v26_retry_tasks
                    WHERE date = ?
                      AND market = ?
                      AND kind = ?
                """, (
                    day.isoformat(),
                    market,
                    kind,
                ))

            log.info(
                "%s %s %s：取得 %d 筆",
                day,
                market,
                kind,
                len(records),
            )

            return True

        except sqlite3.Error as exc:
            log.error(
                "資料庫錯誤：%s",
                exc,
            )

    log.warning(
        "%s %s %s：取得 0 筆，等待重試",
        day,
        market,
        kind,
    )

    with conn:
        conn.execute("""
            INSERT INTO v26_retry_tasks
            (date, market, kind, reason)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(date, market, kind)
            DO UPDATE SET
                reason = excluded.reason
        """, (
            day.isoformat(),
            market,
            kind,
            "API 無資料、解析失敗或寫入失敗",
        ))

    return False


# ==========================================
# 處理指定日期
# ==========================================

def process_day(conn, day, include_inst=True):
    if day.weekday() >= 5:
        return

    for market in ("上市", "上櫃"):
        run_task(
            conn,
            day,
            market,
            "行情",
        )
        time.sleep(1)

    if include_inst:
        for market in ("上市", "上櫃"):
            run_task(
                conn,
                day,
                market,
                "法人",
            )
            time.sleep(1)


# ==========================================
# 重試失敗日期
# ==========================================

def retry_tasks(conn, limit=12):
    rows = conn.execute("""
        SELECT date, market, kind
        FROM v26_retry_tasks
        WHERE date <= ?
        ORDER BY date DESC
        LIMIT ?
    """, (
        (
            date.today() - timedelta(days=1)
        ).isoformat(),
        limit,
    )).fetchall()

    if rows:
        log.info(
            "開始重試 %d 個失敗項目",
            len(rows),
        )

    for day_text, market, kind in rows:
        day = date.fromisoformat(day_text)

        if day.weekday() >= 5:
            continue

        run_task(
            conn,
            day,
            market,
            kind,
        )

        time.sleep(1)


# ==========================================
# 主程式
# ==========================================

def run(days, reset=False):
    today = date.today()

    price_limit = (
        today - timedelta(days=450)
    )

    inst_limit = (
        today - timedelta(days=365)
    )

    with sqlite3.connect(DB) as conn:
        init_db(conn)

        if reset:
            log.warning(
                "--reset 僅重設歷史進度，"
                "不刪除行情與法人資料"
            )

            with conn:
                conn.execute("""
                    DELETE FROM v26_progress
                    WHERE dataset = 'history'
                """)

        # 優先重試失敗資料
        retry_tasks(conn)

        # 更新最近 3 天
        for offset in range(3):
            day = today - timedelta(days=offset)

            if day.weekday() < 5:
                process_day(conn, day)

        # 取得歷史回補進度
        row = conn.execute("""
            SELECT next_day
            FROM v26_progress
            WHERE dataset = 'history'
        """).fetchone()

        cursor = (
            date.fromisoformat(row[0])
            if row
            else today
        )

        processed = 0

        while (
            cursor >= price_limit
            and processed < days
        ):
            if cursor.weekday() < 5:
                process_day(
                    conn,
                    cursor,
                    include_inst=(
                        cursor >= inst_limit
                    ),
                )

            cursor -= timedelta(days=1)
            processed += 1

        # 儲存下次回補位置
        with conn:
            conn.execute("""
                INSERT INTO v26_progress
                (dataset, next_day)
                VALUES ('history', ?)
                ON CONFLICT(dataset)
                DO UPDATE SET
                    next_day = excluded.next_day
            """, (
                cursor.isoformat(),
            ))

        pending = conn.execute("""
            SELECT COUNT(*)
            FROM v26_retry_tasks
        """).fetchone()[0]

        # 檢查目前法人資料量
        inst_stats = conn.execute("""
            SELECT
                market,
                COUNT(*),
                MIN(date),
                MAX(date)
            FROM institutional
            GROUP BY market
            ORDER BY market
        """).fetchall()

        log.info("========== 法人資料統計 ==========")

        for market, count, earliest, latest in inst_stats:
            log.info(
                "%s：%d 筆，日期 %s ~ %s",
                market,
                count,
                earliest,
                latest,
            )

        log.info(
            "本批完成，下一次從 %s 繼續",
            cursor,
        )

        log.info(
            "待重試項目：%d",
            pending,
        )

        log.info(
            "V2.6.3 執行結束"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--days",
        type=int,
        default=10,
    )

    parser.add_argument(
        "--reset",
        action="store_true",
    )

    args = parser.parse_args()

    run(
        days=max(1, min(args.days, 90)),
        reset=args.reset,
    )
