"""匿名站內股票熱門搜尋：只記錄使用者明確送出的有效股票代號。

使用執行個體的 /tmp SQLite，部署重啟會歸零，不代表全台市場搜尋熱度。
不記錄 IP、姓名或自由輸入文字。
"""
import sqlite3
from pathlib import Path

DB = Path("/tmp/taiwan_stock_search_rank.sqlite3")


def record_stock_search(market, code, valid_pairs):
    key = f"{market}:{code}"
    if key not in valid_pairs:
        return False
    with sqlite3.connect(DB, timeout=6) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS stock_searches (
            market TEXT NOT NULL,
            code TEXT NOT NULL,
            count INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (market,code)
        )""")
        conn.execute("""INSERT INTO stock_searches(market,code,count)
            VALUES (?,?,1)
            ON CONFLICT(market,code) DO UPDATE SET count=count+1""", (market,code))
    return True


def top_stock_searches(valid_labels, limit=10):
    if not DB.exists():
        return []
    with sqlite3.connect(DB, timeout=6) as conn:
        rows=conn.execute("""SELECT market,code,count FROM stock_searches
            ORDER BY count DESC, market, code LIMIT ?""", (limit,)).fetchall()
    return [(market,code,valid_labels[f"{market}:{code}"], count)
            for market,code,count in rows if f"{market}:{code}" in valid_labels]
