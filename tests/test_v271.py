import ast
import pathlib
import unittest
import pandas as pd
from price_periods import convert_price_period, chart_tail_count

ROOT = pathlib.Path(__file__).resolve().parents[1]

class ThemeAndPeriodTests(unittest.TestCase):
    def test_all_python_compiles(self):
        for path in [ROOT/"top_nav.py",ROOT/"price_periods.py",ROOT/"pages/1_均線與法人籌碼.py",ROOT/"pages/2_個股技術分析.py"]:
            ast.parse(path.read_text(encoding="utf-8"))

    def test_theme_state_not_bound_to_widget(self):
        source=(ROOT/"top_nav.py").read_text(encoding="utf-8")
        self.assertIn('key="_radar_theme_toggle"',source)
        self.assertIn('st.session_state["radar_light_theme"] = bool',source)
        self.assertNotIn('st.caption("點選上方選單展開功能',source)
        self.assertIn('min-height: 2.75rem',source)

    def test_ohlcv_weekly_and_monthly(self):
        dates=pd.bdate_range("2026-01-01",periods=65)
        df=pd.DataFrame({"date":dates,"open":range(1,66),"high":range(2,67),"low":range(1,66),
                         "close":range(1,66),"volume":[100]*65})
        daily=convert_price_period(df,"日線")
        weekly=convert_price_period(df,"週線")
        monthly=convert_price_period(df,"月線")
        self.assertEqual(len(daily),65)
        self.assertLess(len(monthly),len(weekly))
        self.assertLess(len(weekly),len(daily))
        self.assertAlmostEqual(float(weekly["volume"].sum()),6500)
        self.assertAlmostEqual(float(monthly["volume"].sum()),6500)
        self.assertTrue(pd.notna(daily.iloc[-1]["MA20"]))
        self.assertTrue(pd.isna(monthly.iloc[-1]["MA20"]))

    def test_chart_period_count(self):
        self.assertEqual(chart_tail_count("月線","1年",100),12)
        self.assertEqual(chart_tail_count("日線","全部",65),65)

if __name__ == "__main__":
    unittest.main()
