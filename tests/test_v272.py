"""V2.7.2：日／週／月 K 棒及法人副圖測試。"""
import ast
import pathlib
import unittest

import pandas as pd
from price_periods import convert_price_period
from technical_charts import PANEL_OPTIONS, aggregate_institutional, calculate_kd, chart_view

ROOT = pathlib.Path(__file__).resolve().parents[1]


class CandlestickPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.days = pd.bdate_range("2026-07-01",periods=85)
        cls.ohlc = pd.DataFrame({
            "date":cls.days,
            "open":[100+i for i in range(85)],
            "high":[104+i for i in range(85)],
            "low":[98+i for i in range(85)],
            "close":[102+i for i in range(85)],
            "volume":[1000+i for i in range(85)],
        })

    def test_all_five_options_render_at_every_frequency(self):
        self.assertEqual(len(PANEL_OPTIONS),5)
        dates=self.days
        inst=pd.DataFrame({"date":dates,"foreign_net":[1000]*85,
                           "trust_net":[500]*85,"dealer_net":[-200]*85})
        for freq in ("日線","週線","月線"):
            bars=convert_price_period(self.ohlc,freq)
            for panel in PANEL_OPTIONS:
                chart,warning=chart_view(bars,panel,frequency=freq,inst=inst,calendar=dates)
                self.assertIsNotNone(chart,(freq,panel,warning))
                self.assertTrue(chart.to_dict(),(freq,panel))
            self.assertGreater(len(bars),0)

    def test_kd_requires_nine_bars(self):
        bars=convert_price_period(self.ohlc,"日線")
        result=calculate_kd(bars)
        self.assertTrue(result["K"].iloc[:8].isna().all())
        self.assertTrue(result["D"].iloc[9:].notna().all())
        self.assertTrue(result["K"].iloc[-1] <= 100)

    def test_institutional_missing_day_is_not_zero(self):
        dates=self.days[:7]
        records=pd.DataFrame({"date":dates[:-1],"foreign_net":[1000]*6,
                         "trust_net":[200]*6,"dealer_net":[100]*6})
        complete=aggregate_institutional(records, dates,"週線")
        self.assertTrue(complete["外資買賣超"].isna().any())
        self.assertTrue((complete["外資買賣超"].dropna()>0).all())

    def test_pages_use_same_chart(self):
        for path in ("pages/1_均線與法人籌碼.py","pages/2_個股技術分析.py"):
            code=(ROOT/path).read_text(encoding="utf-8")
            ast.parse(code)
            self.assertIn("chart_view(",code)
            self.assertIn("下方指標切換",code)
            self.assertIn("timeframe",code)
        self.assertIn("open,high,low,close,volume",
                      (ROOT/"pages/1_均線與法人籌碼.py").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
