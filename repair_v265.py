
# -*- coding: utf-8 -*-
"""
台股 AI 突破雷達 V2.6.5
上市／上櫃三大法人資料缺口檢查與修復

檢查：
    python repair_v265.py --days 45 --limit 8

正式修復：
    python repair_v265.py --days 45 --limit 8 --apply
"""

import argparse
import datetime as dt
import logging
import re
import sqlite3
import time
from pathlib import Path

import requests


DB_PATH = Path(__file__).resolve().parent / "twstock.sqlite3"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("repair_v265")

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; TaiwanStockRadar/2.6.5)",
    "Accept": "application/json",
})


def number(value):
    """將公開資料的千分位數字轉為整數。"""
    if isinstance(value, bool):
        raise ValueError("不接受布林值")
    if isinstance(value, (int, float)):
        return int(value)
    text = str(value).strip().replace(",", "")
    text = text.replace("＋", "+").replace("－", "-")
    text = text.replace("−", "-").replace(" ", "")
    if text in ("", "--", "---", "N/A", "null", "None"):
        raise ValueError("缺少數字")
    return int(float(text))


def stock_code(value):
    text = str(value).strip()
    return bool(re.fullmatch(r"\d{4,6}", text))


def normalize_header(value):
    return re.sub(r"[\s\u3000()（）]", "", str(value))


def find_column(headers, candidates):
    normalized = [normalize_header(h) for h in headers]
    for candidate in candidates:
        target = normalize_header(candidate)
        if target in normalized:
            return normalized.index(target)
    return None


def get_json(url, params):
    response = SESSION.get(url, params=params, timeout=25)
    response.raise_for_status()
    return response.json()


def parse_table(data):
    """支援證交所及櫃買中心常見的 JSON 表格結構。"""
    if not isinstance(data, dict):
        return [], []

    candidates = [data]
    for key in ("tables", "results"):
        value = data.get(key)
        if isinstance(value, list):
            candidates.extend(
                item for item in value if isinstance(item, dict)
            )

    for item in candidates:
        headers = item.get("fields") or item.get("columns")
        rows = item.get("data") or item.get("aaData")

        if not isinstance(headers, list) or not isinstance(rows, list):
            continue

        headers = [
            h.get("title", h.get("name", ""))
            if isinstance(h, dict) else str(h)
            for h in headers
        ]
        return headers, rows

    return [], []


def parse_institutional(data, day, market):
    headers, rows = parse_table(data)

    if not headers or not rows:
        return []

    code_i = find_column(headers, [
        "證券代號", "代號", "股票代號",
    ])
    name_i = find_column(headers, [
        "證券名稱", "名稱", "股票名稱",
    ])

    # 只接受三大法人各自的買賣超欄位，
    # 不使用總計欄位冒充外資、投信或自營商。
    foreign_i = find_column(headers, [
        "外陸資買賣超股數(不含外資自營商)",
        "外陸資買賣超股數",
        "外資及陸資買賣超股數",
        "外資買賣超股數",
        "外資及陸資(不含外資自營商)買賣超股數",
        "外資及陸資買賣超",
        "外資買賣超",
    ])
    trust_i = find_column(headers, [
        "投信買賣超股數",
        "投信買賣超",
    ])
    dealer_i = find_column(headers, [
        "自營商買賣超股數",
        "自營商買賣超",
        "自營商買賣超合計",
        "自營商買賣超股數(自行買賣+避險)",
    ])

    # 若只有自行買賣及避險兩欄，兩者相加。
    dealer_self_i = find_column(headers, [
        "自營商買賣超股數(自行買賣)",
        "自營商(自行買賣)買賣超股數",
        "自營商自行買賣買賣超",
    ])
    dealer_hedge_i = find_column(headers, [
        "自營商買賣超股數(避險)",
        "自營商(避險)買賣超股數",
        "自營商避險買賣超",
    ])

    required = [code_i, name_i, foreign_i, trust_i]
    has_dealer = dealer_i is not None or (
        dealer_self_i is not None and dealer_hedge_i is not None
    )

    if any(i is None for i in required) or not has_dealer:
        raise ValueError(
            f"{market} 法人欄位不符合預期：{headers}"
        )

    result = []

    for row in rows:
        try:
            if isinstance(row, dict):
                row = [
                    row.get(h, "") for h in headers
                ]

            code = str(row[code_i]).strip()
            if not stock_code(code):
                continue

            foreign = number(row[foreign_i])
            trust = number(row[trust_i])

            if dealer_i is not None:
                dealer = number(row[dealer_i])
            else:
                dealer = (
                    number(row[dealer_self_i])
                    + number(row[dealer_hedge_i])
                )

            result.append({
                "date": day.isoformat(),
                "market": market,
                "code": code,
                "name": str(row[name_i]).strip(),
                "foreign_net": foreign,
                "trust_net": trust,
                "dealer_net": dealer,
            })
        except (ValueError, TypeError, IndexError, KeyError):
            continue

    return result


def fetch_twse(day):
    data = get_json(
        "https://www.twse.com.tw/rwd/zh/fund/T86",
        {
            "date": day.strftime("%Y%m%d"),
            "selectType": "ALLBUT0999",
            "response": "json",
        },
    )
    return parse_institutional(data, day, "上市")


def fetch_tpex(day):
    """使用 V2.6.3 已驗證的上櫃法人 API 與解析器。"""
    from backfill_v26 import task_config

    url, params, parser = task_config(day, "上櫃", "法人")
    data = get_json(url, params)

    records = parser(data, day)

    result = []
    for row in records:
        result.append({
            "date": row[0],
            "market": row[1],
            "code": row[2],
            "name": row[3],
            "foreign_net": row[4],
            "trust_net": row[5],
            "dealer_net": row[6],
        })

    return result
    date_text = day.strftime("%Y/%m/%d")
    roc_date = (
        f"{day.year - 1911}/{day.month:02d}/{day.day:02d}"
    )

    sources = [
        (
            "https://www.tpex.org.tw/www/zh-tw/3insti/daily",
            {"date": date_text},
        ),
        (
            "https://www.tpex.org.tw/web/stock/3insti/daily_trade/"
            "3itrade_hedge_result.php",
            {
                "l": "zh-tw",
                "se": "EW",
                "t": "D",
                "d": roc_date,
            },
        ),
    ]

    last_error = None

    for url, params in sources:
        try:
            data = get_json(url, params)
            result = parse_institutional(data, day, "上櫃")
            if result:
                return result
        except (requests.RequestException, ValueError) as exc:
            last_error = exc

    if last_error:
        log.warning("%s 上櫃來源回應：%s", day, last_error)

    return []


def table_columns(conn, table):
    return {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})")
    }


def prepare_database(conn):
    tables = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }

    if "institutional" not in tables:
        conn.execute("""
            CREATE TABLE institutional (
                date TEXT NOT NULL,
                market TEXT NOT NULL,
                code TEXT NOT NULL,
                name TEXT,
                foreign_net INTEGER,
                trust_net INTEGER,
                dealer_net INTEGER,
                PRIMARY KEY (date, market, code)
            )
        """)
        conn.commit()

    cols = table_columns(conn, "institutional")

    required = {
        "date", "market", "code", "name",
        "foreign_net", "trust_net",
    }
    missing = required - cols

    if missing:
        raise RuntimeError(
            "institutional 資料表缺少欄位：" + str(missing)
        )

    if "dealer_net" not in cols:
        conn.execute(
            "ALTER TABLE institutional "
            "ADD COLUMN dealer_net INTEGER"
        )
        conn.commit()


def existing_counts(conn, day, market):
    row = conn.execute(
        """
        SELECT
            COUNT(*),
            SUM(
                CASE WHEN
                    foreign_net IS NOT NULL
                    AND trust_net IS NOT NULL
                    AND dealer_net IS NOT NULL
                THEN 1 ELSE 0 END
            )
        FROM institutional
        WHERE date = ? AND market = ?
        """,
        (day.isoformat(), market),
    ).fetchone()

    return int(row[0] or 0), int(row[1] or 0)


def save_rows(conn, rows):
    if not rows:
        return 0

    # 不覆蓋已存在且完整的法人紀錄。
    # 只補入缺少的資料或修復 NULL 欄位。
    count = 0

    with conn:
        for item in rows:
            old = conn.execute(
                """
                SELECT foreign_net, trust_net, dealer_net
                FROM institutional
                WHERE date = ? AND market = ? AND code = ?
                LIMIT 1
                """,
                (item["date"], item["market"], item["code"]),
            ).fetchone()

            if old is not None and all(
                value is not None for value in old
            ):
                continue

            if old is None:
                conn.execute(
                    """
                    INSERT INTO institutional (
                        date, market, code, name,
                        foreign_net, trust_net, dealer_net
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        item["date"],
                        item["market"],
                        item["code"],
                        item["name"],
                        item["foreign_net"],
                        item["trust_net"],
                        item["dealer_net"],
                    ),
                )
            else:
                conn.execute(
                    """
                    UPDATE institutional
                    SET
                        name = COALESCE(NULLIF(name, ''), ?),
                        foreign_net = COALESCE(foreign_net, ?),
                        trust_net = COALESCE(trust_net, ?),
                        dealer_net = COALESCE(dealer_net, ?)
                    WHERE date = ? AND market = ? AND code = ?
                    """,
                    (
                        item["name"],
                        item["foreign_net"],
                        item["trust_net"],
                        item["dealer_net"],
                        item["date"],
                        item["market"],
                        item["code"],
                    ),
                )
            count += 1

    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=45)
    parser.add_argument("--limit", type=int, default=8)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    if args.days < 1 or args.limit < 1:
        parser.error("--days 與 --limit 必須大於零")

    if not DB_PATH.exists():
        raise SystemExit(
            f"找不到資料庫：{DB_PATH}"
        )

    today = dt.datetime.now(
        dt.timezone(dt.timedelta(hours=8))
    ).date()

    start = today - dt.timedelta(days=args.days - 1)

    log.info("V2.6.5 法人資料缺口修復")
    log.info("模式：%s", "正式修復" if args.apply else "僅檢查")
    log.info("檢查範圍：%s 至 %s", start, today)
    log.info("本次最多處理 %s 個市場日期組合", args.limit)

    checked = 0
    repaired = 0
    failed = 0
    skipped = 0

    with sqlite3.connect(DB_PATH) as conn:
        prepare_database(conn)

        day = today

        while day >= start and checked < args.limit:
            # 週六、週日不查詢；國定假日則由來源回應判斷。
            if day.weekday() >= 5:
                day -= dt.timedelta(days=1)
                continue

            for market, fetcher in (
                ("上市", fetch_twse),
                ("上櫃", fetch_tpex),
            ):
                if checked >= args.limit:
                    break

                total, complete = existing_counts(
                    conn, day, market
                )

                # 已有足量且完整的資料時不重複抓取。
                # 門檻僅供初步檢查，不代表已驗證完整率。
                minimum = 500 if market == "上市" else 300

                if complete >= minimum and complete == total:
                    skipped += 1
                    continue

                checked += 1

                log.info(
                    "%s %s：現有 %s 筆，完整 %s 筆",
                    day, market, total, complete
                )

                try:
                    rows = fetcher(day)

                    if not rows:
                        failed += 1
                        log.warning(
                            "%s %s：未取得可驗證的法人資料，"
                            "保留原資料，待下次重試",
                            day, market
                        )
                        continue

                    log.info(
                        "%s %s：來源取得 %s 筆",
                        day, market, len(rows)
                    )

                    if args.apply:
                        count = save_rows(conn, rows)
                        repaired += count
                        log.info(
                            "%s %s：新增或補齊 %s 筆",
                            day, market, count
                        )
                    else:
                        log.info(
                            "%s %s：檢查完成，未寫入資料庫",
                            day, market
                        )

                except Exception as exc:
                    failed += 1
                    log.error(
                        "%s %s：處理失敗：%s",
                        day, market, exc
                    )

                time.sleep(1)

            day -= dt.timedelta(days=1)

    log.info("========== 執行結果 ==========")
    log.info("實際檢查組合：%s", checked)
    log.info("略過已有資料組合：%s", skipped)
    log.info("來源失敗或無法驗證：%s", failed)
    log.info("新增或補齊資料筆數：%s", repaired)

    if not args.apply:
        log.info("目前為檢查模式，未進行正式法人資料回補")

    if failed:
        log.warning(
            "仍有 %s 個組合未成功取得資料，需後續處理",
            failed
        )

    log.info("V2.6.5 執行結束")


if __name__ == "__main__":
    main()
