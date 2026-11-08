"""V2.7.4: verify chart annotations, stock links, and resumable MA240 backfill."""
import ast
import pathlib
import sqlite3
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


class ChartAndBackfillTests(unittest.TestCase):
    def test_high_low_labels(self):
        code=(ROOT/"technical_charts.py").read_text(encoding="utf-8")
        self.assertIn('df["high"].idxmax()',code)
        self.assertIn('df["low"].idxmin()',code)
        self.assertIn("labels_high",code)
        self.assertIn("labels_low",code)
        ast.parse(code)

    def test_linked_name_and_hidden_extra_columns(self):
        code=(ROOT/"pages/1_均線與法人籌碼.py").read_text(encoding="utf-8")
        self.assertIn('shown["name"]',code)
        self.assertIn('LinkColumn("股票名稱（點擊看圖）"',code)
        self.assertIn('display_text=r"#([^#]+)$"',code)
        ast.parse(code)

    def test_requested_footer_removed(self):
        code=(ROOT/"app.py").read_text(encoding="utf-8")
        self.assertNotIn("評分是透明規則模型，不是機器學習預測勝率",code)

    def test_missing_days_skips_existing_market_data(self):
        source=(ROOT/"backfill_ma240.py").read_text(encoding="utf-8")
        node=ast.parse(source)
        fn=next(n for n in node.body if isinstance(n,ast.FunctionDef) and n.name=="missing_jobs")
        import pandas as pd
        scope={"pd":pd}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),"<test>","exec"),scope)
        conn=sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE daily(date TEXT,market TEXT,code TEXT)")
        rows=[("2026-11-06","上市",str(i)) for i in range(501)]
        conn.executemany("INSERT INTO daily VALUES (?,?,?)",rows)
        jobs=scope["missing_jobs"](conn,pd.Timestamp("2026-11-06"),pd.Timestamp("2026-11-06"))
        self.assertEqual(jobs,[(pd.Timestamp("2026-11-06").date(),"上櫃")])
        conn.close()


if __name__=="__main__":
    unittest.main()
