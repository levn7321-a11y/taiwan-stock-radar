"""BIAS(6/12/24) indicators and uptime monitor regression coverage."""
import ast
from pathlib import Path
import unittest

import pandas as pd
from price_periods import convert_price_period
from technical_charts import PANEL_OPTIONS, chart_view

ROOT = Path(__file__).resolve().parents[1]


class BiasUptimeTests(unittest.TestCase):
    def setUp(self):
        dates = pd.bdate_range("2025-01-02", periods=330)
        self.prices = pd.DataFrame({
            "date": dates,
            "open": range(101, 431),
            "high": range(102, 432),
            "low": range(99, 429),
            "close": range(100, 430),
            "volume": [1500]*330,
        })

    def test_bias_formula_and_incomplete_averages(self):
        frame = convert_price_period(self.prices, "日線")
        self.assertEqual(len(frame), 330)
        for period in (6, 12, 24):
            col = f"BIAS{period}"
            self.assertTrue(frame[col].iloc[:period-1].isna().all())
            self.assertTrue(pd.notna(frame[col].iloc[period-1]))
            expected = (
                frame["close"].iloc[-1] /
                frame["close"].iloc[-period:].mean() - 1
            ) * 100
            self.assertAlmostEqual(frame[col].iloc[-1], expected, places=9)

    def test_bias_uses_weekly_and_monthly_close(self):
        for freq in ("週線", "月線"):
            frame = convert_price_period(self.prices, freq)
            for period in (6, 12, 24):
                expected = (frame["close"].iloc[-1] / frame["close"].iloc[-period:].mean()-1)*100
                if len(frame)>=period:
                    self.assertAlmostEqual(frame[f"BIAS{period}"].iloc[-1],expected,places=9)
            chart,warning = chart_view(frame, "乖離率", frequency=freq)
            self.assertEqual(warning, "")
            self.assertIsNotNone(chart.to_dict())

    def test_bias_is_plotted_after_lookback_trim(self):
        frame=convert_price_period(self.prices,"日線")
        tail=frame.tail(30)
        self.assertTrue(pd.notna(tail["BIAS24"].iloc[0]))
        chart,warning=chart_view(tail,"乖離率",frequency="日線")
        self.assertEqual(warning,"")
        self.assertIn("乖離率",PANEL_OPTIONS)
        spec=chart.to_dict()
        self.assertTrue(spec["vconcat"][1]["layer"])

    def test_all_three_pages_have_option(self):
        for p in ("pages/1_均線與法人籌碼.py",
                  "pages/2_個股技術分析.py",
                  "pages/3_自選個股.py"):
            src=(ROOT/p).read_text(encoding="utf-8")
            self.assertIn('if (indicator or "成交量") == "乖離率":',src)
            ast.parse(src)

    def test_monitor_checks_actual_browser_not_only_http(self):
        src=(ROOT/"monitor_site.py").read_text(encoding="utf-8")
        workflow=(ROOT/".github/workflows/site_monitor.yml").read_text(encoding="utf-8")
        self.assertIn("page.goto(url,",src)
        self.assertIn('Error running app',src)
        self.assertIn("/_stcore/health",src)
        self.assertIn('cron: "*/30 * * * *"',workflow)
        self.assertIn("gh issue create",workflow)
        self.assertIn("gh issue close",workflow)
        ast.parse(src)


if __name__ == "__main__":
    unittest.main()
