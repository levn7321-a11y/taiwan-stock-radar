"""Missing OHLC rows should not blank an otherwise usable candlestick chart."""
import ast
from pathlib import Path
import unittest

import pandas as pd
from price_periods import convert_price_period
from technical_charts import chart_view, valid_ohlc_bars

ROOT=Path(__file__).resolve().parents[1]


class MissingOHLCBarTests(unittest.TestCase):
    def setUp(self):
        dates = pd.bdate_range("2026-06-01",periods=70)
        self.df = pd.DataFrame({
            "date": dates, "open": [float(x) for x in range(10,80)],
            "high": [float(x)+2 for x in range(10,80)],
            "low": [float(x)-1 for x in range(10,80)],
            "close": [float(x)+1 for x in range(10,80)],
            "volume": [1000]*70,
        })

    def test_one_missing_date_does_not_hide_all_candles(self):
        self.df.loc[7,"open"]=None
        bars=convert_price_period(self.df,"日線")
        cleaned=valid_ohlc_bars(bars)
        self.assertEqual(len(cleaned),69)
        graphic,warning=chart_view(bars,"成交量")
        self.assertIsNotNone(graphic)
        self.assertIn("1 根 K 棒",warning)
        self.assertIn(self.df.loc[7,"date"].date().isoformat(),warning)
        self.assertTrue(graphic.to_dict()["vconcat"])

    def test_missing_latest_bar_preserves_previous_chart(self):
        self.df.loc[69,"high"]=float("nan")
        bars=convert_price_period(self.df,"日線")
        graphic,warning=chart_view(bars,"乖離率")
        self.assertIsNotNone(graphic)
        self.assertEqual(valid_ohlc_bars(bars).index[-1],self.df.loc[68,"date"])
        self.assertIn("1 根 K 棒",warning)

    def test_no_valid_bars_returns_explanatory_warning(self):
        self.df["low"]=float("nan")
        bars=convert_price_period(self.df,"日線")
        graphic,warning=chart_view(bars,"成交量")
        self.assertIsNone(graphic)
        self.assertIn("沒有可繪製的有效 K 棒",warning)

    def test_monthly_can_aggregate_valid_days(self):
        self.df.loc[3,"open"]=None
        bars=convert_price_period(self.df,"月線")
        graphic,warning=chart_view(bars,"成交量",frequency="月線")
        self.assertIsNotNone(graphic)
        self.assertEqual(warning,"")

    def test_all_three_pages_align_latest_candle(self):
        for p in ("pages/1_均線與法人籌碼.py","pages/2_個股技術分析.py","pages/3_自選個股.py"):
            s=(ROOT/p).read_text(encoding="utf-8")
            ast.parse(s)
            self.assertIn("valid_ohlc_bars(",s)


if __name__=="__main__":
    unittest.main()
