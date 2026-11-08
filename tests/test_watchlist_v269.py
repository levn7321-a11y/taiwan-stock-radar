# -*- coding: utf-8 -*-
"""V2.6.9 regression tests without launching a Streamlit web server."""
import ast
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd

PAGE = Path(__file__).resolve().parents[1] / "pages" / "3_自選個股.py"
TREE = ast.parse(PAGE.read_text(encoding="utf-8"), filename=str(PAGE))
NAMES = {"parse_watch", "load_stocks", "load_recent", "load_inst", "summary_rows"}
FUNCS = [node for node in TREE.body if isinstance(node, ast.FunctionDef) and node.name in NAMES]
assert len(FUNCS) == len(NAMES)
# @st.cache_data is a UI decorator; ignore it for deterministic database unit tests.
for node in FUNCS:
    node.decorator_list = []
module = ast.fix_missing_locations(ast.Module(body=FUNCS, type_ignores=[]))
ns = {"re": __import__("re"), "pd": pd, "sqlite3": sqlite3, "MAX_WATCH": 50,
      "ID_PATTERN": __import__("re").compile(r"^(上市|上櫃):([A-Za-z0-9]{4,6})$")}
exec(compile(module, str(PAGE), "exec"), ns)


class WatchlistTests(unittest.TestCase):
    def test_parse_watch_sanitizes_and_deduplicates(self):
        values = ns["parse_watch"]("上市:2330,上市:2330,上櫃:6488,drop table,上市:0")
        self.assertEqual(values, ["上市:2330", "上櫃:6488"])

    def test_watch_limit(self):
        codes = ",".join("上市:%04d" % i for i in range(1000, 1060))
        self.assertEqual(len(ns["parse_watch"](codes)), 50)

    def test_sql_and_summary_only_watchlist(self):
        with tempfile.TemporaryDirectory() as root:
            db = Path(root) / "twstock.sqlite3"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE daily (date TEXT, market TEXT, code TEXT, name TEXT, open REAL, high REAL, low REAL, close REAL, volume INTEGER)")
                conn.execute("CREATE TABLE institutional (date TEXT, market TEXT, code TEXT, foreign_net INTEGER, trust_net INTEGER, dealer_net INTEGER)")
                conn.executemany("INSERT INTO daily VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
                    ("2026-11-05", "上市", "2330", "台積電", 995, 1010, 990, 1000, 8000),
                    ("2026-11-06", "上市", "2330", "台積電", 1040, 1060, 1030, 1050, 9000),
                    ("2026-11-06", "上市", "2317", "鴻海", 198, 205, 195, 200, 2000),
                    ("2026-11-06", "上櫃", "6488", "環球晶", 398, 402, 393, 400, 3000)])
                conn.executemany("INSERT INTO institutional VALUES (?, ?, ?, ?, ?, ?)", [
                    ("2026-11-06", "上市", "2330", 10000, -2000, 500),
                    ("2026-11-06", "上市", "2317", 20000, 0, 0)])
            keys = ("上市:2330", "上櫃:6488")
            prices = ns["load_recent"](str(db), 1, keys)
            inst = ns["load_inst"](str(db), 1, keys)
            board = ns["summary_rows"](prices, inst, keys)
            self.assertEqual(board["代號"].tolist(), ["2330", "6488"])
            self.assertAlmostEqual(board.iloc[0]["漲跌幅%"], 5.0)
            self.assertAlmostEqual(board.iloc[0]["三大法人(張)"], 8.5)
            self.assertTrue(pd.isna(board.iloc[1]["三大法人(張)"]))
            self.assertNotIn("2317", board["代號"].tolist())


if __name__ == "__main__":
    unittest.main()
