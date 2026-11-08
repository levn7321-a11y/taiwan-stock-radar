"""Checks for V2.7.5 home indices, top search, trust chart and watchlist K-lines."""
import ast
import pathlib
import unittest
from market_indices import parse_twse, parse_tpex

ROOT = pathlib.Path(__file__).resolve().parents[1]


class V275Tests(unittest.TestCase):
    def test_twse_industry_index_parser(self):
        rows = [
            {"日期":"1151106","指數":"發行量加權股價指數","收盤指數":"28,500.40","漲跌":"+","漲跌點數":"100.50"},
            {"日期":"1151106","指數":"金融保險類指數","收盤指數":"2,020.11","漲跌":"-","漲跌點數":"5.20"},
        ]
        result = parse_twse(rows)
        self.assertEqual(result["大盤加權指數"]["date"], "2026-11-06")
        self.assertAlmostEqual(result["金融保險類股指數"]["change"], -5.2)

    def test_tpex_index_parser(self):
        row = {"資料日期":"1151106","收市指數":"300.52","指數漲跌":"-1.32"}
        self.assertAlmostEqual(parse_tpex([row])["close"], 300.52)
        self.assertIsNone(parse_tpex([]))

    def test_watch_chart_links_and_global_search(self):
        w = (ROOT / "pages/3_自選個股.py").read_text(encoding="utf-8")
        nav = (ROOT / "top_nav.py").read_text(encoding="utf-8")
        p = (ROOT / "pages/1_均線與法人籌碼.py").read_text(encoding="utf-8")
        self.assertIn('chart_view(', w)
        self.assertIn('st.column_config.LinkColumn("股票名稱（點擊看圖表）"', w)
        self.assertIn('st.switch_page("pages/1_均線與法人籌碼.py")', nav)
        self.assertIn('global_selected_stock', p)

    def test_trust_institutional_option(self):
        src = (ROOT / "technical_charts.py").read_text(encoding="utf-8")
        self.assertIn('"投信買賣超"', src)
        self.assertIn('frame["投信買賣超"] = frame["trust_net"]', src)

    def test_all_changed_python_compiles(self):
        for path in ("app.py", "market_indices.py", "top_nav.py", "technical_charts.py",
                     "pages/1_均線與法人籌碼.py", "pages/3_自選個股.py"):
            ast.parse((ROOT / path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
