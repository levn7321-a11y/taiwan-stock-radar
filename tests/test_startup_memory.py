"""Ensure the full 240-day data survives while Streamlit loads bounded views."""
import ast
import sqlite3
import tempfile
import unittest
from pathlib import Path

import pandas as pd
from ranking_snapshot import snapshot_ranking

ROOT=Path(__file__).resolve().parents[1]


class BoundedAppTests(unittest.TestCase):
    def test_snapshot_matches_real_240_day_average(self):
        with tempfile.TemporaryDirectory() as d:
            db=Path(d)/"sample.sqlite3"
            dates=pd.bdate_range("2025-11-01",periods=240)
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE daily(date TEXT,market TEXT,code TEXT,name TEXT,open REAL,high REAL,low REAL,close REAL,volume REAL)")
                records=[
                    (dt.strftime("%Y-%m-%d"),"上市","2330","台積電", float(i),float(i+1),float(i-1),float(i),1000)
                    for i,dt in enumerate(dates,1)
                ]
                records += [(dates[-1].strftime("%Y-%m-%d"),"上櫃","9999","測試股",5,6,4,5,10)]
                conn.executemany("INSERT INTO daily VALUES (?,?,?,?,?,?,?,?,?)",records)
            board=snapshot_ranking(db)
            first=board.loc[board.code=="2330"].iloc[0]
            self.assertEqual(len(board),2)
            self.assertAlmostEqual(first["MA240"],120.5)
            self.assertAlmostEqual(first["MA20"],230.5)
            self.assertTrue(pd.isna(board.loc[board.code=="9999","MA240"].iloc[0]))

    def test_home_avoids_full_history(self):
        src=(ROOT/"app.py").read_text(encoding="utf-8")
        self.assertIn("load_home_scan(",src)
        self.assertIn("LIMIT 100",src)
        self.assertNotIn("df = load()",src)

    def test_analysis_loads_full_selected_stock(self):
        src=(ROOT/"pages/1_均線與法人籌碼.py").read_text(encoding="utf-8")
        self.assertIn("LIMIT 320",src)
        self.assertIn("snapshot_ranking",src)
        self.assertIn("LIMIT 35",src)

    def test_python_syntax(self):
        for p in ("app.py","ranking_snapshot.py","pages/1_均線與法人籌碼.py",
                  "pages/4_法人買賣超排行.py","pages/5_近期高分股票.py"):
            ast.parse((ROOT/p).read_text(encoding="utf-8"))


if __name__=="__main__":
    unittest.main()
