
import sqlite3
from datetime import date, timedelta
from pathlib import Path

DB = Path(__file__).resolve().parent / "twstock.sqlite3"
TODAY = date.today()
START_365 = (TODAY - timedelta(days=364)).isoformat()


def query(conn, sql, params=()):
    return conn.execute(sql, params).fetchall()


def tables(conn):
    return {
        row[0]
        for row in query(
            conn,
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def columns(conn, table):
    return {
        row[1]
        for row in conn.execute(f"PRAGMA table_info({table})")
    }


def section(title):
    print("\n" + "=" * 65)
    print(title)
    print("=" * 65)


def show_market_summary(conn, table):
    section(f"{table} 市場資料統計")

    sql = f"""
        SELECT
            market,
            COUNT(*) AS rows_count,
            COUNT(DISTINCT code) AS stocks,
            COUNT(DISTINCT date) AS trading_days,
            MIN(date) AS first_date,
            MAX(date) AS last_date
        FROM {table}
        GROUP BY market
        ORDER BY market
    """

    for row in query(conn, sql):
        market, count, stocks, days, first, last = row
        print(
            f"{market}："
            f"{count:,} 筆，"
            f"{stocks:,} 檔股票，"
            f"{days} 個日期"
        )
        print(f"  最早：{first}")
        print(f"  最新：{last}")


def show_institutional_counts(conn):
    section("三大法人有效資料筆數")

    cols = columns(conn, "institutional")

    names = [
        ("foreign_net", "外資"),
        ("trust_net", "投信"),
        ("dealer_net", "自營商"),
    ]

    for market in ("上市", "上櫃"):
        print(f"\n【{market}】")

        for field, label in names:
            if field not in cols:
                print(f"{label}：缺少欄位 {field}")
                continue

            sql = f"""
                SELECT
                    COUNT(*),
                    COUNT({field}),
                    COUNT(DISTINCT CASE
                        WHEN {field} IS NOT NULL THEN date
                    END),
                    MIN(CASE
                        WHEN {field} IS NOT NULL THEN date
                    END),
                    MAX(CASE
                        WHEN {field} IS NOT NULL THEN date
                    END)
                FROM institutional
                WHERE market = ?
                  AND date >= ?
            """

            total, valid, days, first, last = query(
                conn, sql, (market, START_365)
            )[0]

            print(
                f"{label}：{valid:,} 筆有效資料"
                f"／{total:,} 筆法人紀錄"
            )
            print(
                f"  涵蓋 {days} 個日期"
                f"｜{first or '無'} ~ {last or '無'}"
            )


def show_recent_coverage(conn):
    section("最近365天行情與法人日期覆蓋檢查")

    for market in ("上市", "上櫃"):
        price_dates = {
            row[0]
            for row in query(
                conn,
                """
                SELECT DISTINCT date
                FROM daily
                WHERE market = ? AND date >= ?
                """,
                (market, START_365),
            )
        }

        inst_dates = {
            row[0]
            for row in query(
                conn,
                """
                SELECT DISTINCT date
                FROM institutional
                WHERE market = ? AND date >= ?
                """,
                (market, START_365),
            )
        }

        missing_inst = sorted(
            price_dates - inst_dates,
            reverse=True,
        )

        extra_inst = sorted(
            inst_dates - price_dates,
            reverse=True,
        )

        print(f"\n【{market}】")
        print(f"行情日期：{len(price_dates)} 天")
        print(f"法人日期：{len(inst_dates)} 天")
        print(
            f"有行情但沒有法人資料："
            f"{len(missing_inst)} 天"
        )

        if missing_inst:
            print(
                "缺少法人日期（最多顯示20天）："
            )
            print("、".join(missing_inst[:20]))

        if extra_inst:
            print(
                "有法人但沒有行情的日期："
                f"{len(extra_inst)} 天"
            )
            print("、".join(extra_inst[:10]))

        if not price_dates:
            print(
                "注意：沒有行情日期可供比較，"
                "不能判定資料完整。"
            )

    print(
        "\n說明：以上以資料庫現有行情日期"
        "作為比較基準。"
    )
    print(
        "若行情與法人同一天都缺少，"
        "此檢查不會自動辨識該日期。"
    )


def show_recent_quality(conn):
    section("最近365天法人資料品質")

    cols = columns(conn, "institutional")

    fields = [
        f for f in (
            "foreign_net", "trust_net", "dealer_net"
        )
        if f in cols
    ]

    for market in ("上市", "上櫃"):
        print(f"\n【{market}】")

        for field in fields:
            result = query(
                conn,
                f"""
                SELECT COUNT(*)
                FROM institutional
                WHERE market = ?
                  AND date >= ?
                  AND {field} IS NULL
                """,
                (market, START_365),
            )[0][0]

            print(f"{field} 空值：{result:,} 筆")

        result = query(
            conn,
            """
            SELECT COUNT(*)
            FROM (
                SELECT date, market, code
                FROM institutional
                WHERE market = ? AND date >= ?
                GROUP BY date, market, code
                HAVING COUNT(*) > 1
            )
            """,
            (market, START_365),
        )[0][0]

        print(f"重複股票日期組合：{result:,} 組")


def show_ma240(conn):
    section("日線 MA240 資料完整度")

    for market in ("上市", "上櫃"):
        result = query(
            conn,
            """
            SELECT
                COUNT(*),
                SUM(CASE WHEN days_count >= 240
                    THEN 1 ELSE 0 END),
                SUM(CASE WHEN days_count < 240
                    THEN 1 ELSE 0 END)
            FROM (
                SELECT code, COUNT(DISTINCT date) days_count
                FROM daily
                WHERE market = ?
                GROUP BY code
            )
            """,
            (market,),
        )[0]

        total, enough, insufficient = result

        print(
            f"{market}：共 {total or 0:,} 檔"
        )
        print(
            f"  達到240個交易日：{enough or 0:,} 檔"
        )
        print(
            f"  不足240個交易日："
            f"{insufficient or 0:,} 檔"
        )

    print(
        "\n注意：此處僅檢查日期數量，"
        "未逐檔驗證交易日連續性。"
    )


def show_progress(conn):
    if "v26_progress" not in tables(conn):
        return

    section("V2.6 歷史回補進度")

    rows = query(
        conn,
        "SELECT dataset, next_day FROM v26_progress"
    )

    for dataset, next_day in rows:
        print(
            f"{dataset}："
            f"下一次從 {next_day} 繼續"
        )


def main():
    print("台股 AI 突破雷達 V2.6")
    print("行情與法人資料庫健康檢查")
    print(f"檢查日期：{TODAY.isoformat()}")
    print(f"365天起始日：{START_365}")

    if not DB.exists():
        raise SystemExit(
            f"找不到資料庫：{DB}"
        )

    print(f"資料庫大小：{DB.stat().st_size:,} bytes")

    with sqlite3.connect(
        f"file:{DB}?mode=ro",
        uri=True
    ) as conn:
        found = tables(conn)

        print("資料表：", ", ".join(sorted(found)))

        if "daily" not in found:
            raise SystemExit("錯誤：缺少 daily 資料表")

        show_market_summary(conn, "daily")

        if "institutional" not in found:
            section("法人資料")
            print(
                "尚未建立 institutional 資料表，"
                "無法檢查法人籌碼。"
            )
        else:
            show_market_summary(
                conn, "institutional"
            )
            show_institutional_counts(conn)
            show_recent_coverage(conn)
            show_recent_quality(conn)

        show_ma240(conn)
        show_progress(conn)

    section("檢查完成")
    print(
        "本程式僅讀取資料庫，不會修改資料。"
    )


if __name__ == "__main__":
    main()
