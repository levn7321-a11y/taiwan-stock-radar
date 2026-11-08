"""MA240 回補工作流程：批次與交易日數停止條件測試。"""
import ast
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import backfill_ma240 as ma

ROOT = Path(__file__).resolve().parents[1]


class HistoryBackfillTests(unittest.TestCase):
    def test_files_parse(self):
        for path in ("backfill_ma240.py", "backfill_v26.py"):
            ast.parse((ROOT / path).read_text(encoding="utf-8"))

    def test_market_sessions_count_real_unique_dates(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Path(folder) / "stocks.sqlite3"
            with sqlite3.connect(db) as conn:
                conn.execute("CREATE TABLE daily (date TEXT,market TEXT,close REAL)")
                conn.executemany("INSERT INTO daily VALUES (?,?,?)", [
                    ("2026-11-04", "上市", 100),
                    ("2026-11-04", "上市", 200),
                    ("2026-11-05", "上市", 0),
                    ("2026-11-05", "上櫃", 55),
                ])
            self.assertEqual(ma.market_sessions(db), {"上市": 1, "上櫃": 1})

    def test_does_not_refetch_when_completed(self):
        with patch.object(ma, "market_sessions", return_value={"上市": 260, "上櫃": 265}):
            with patch.object(ma, "run") as runner:
                self.assertEqual(ma.backfill_until(260, 3, 90)["上市"], 260)
                runner.assert_not_called()

    def test_resumable_batches_when_history_short(self):
        state = [
            {"上市": 80, "上櫃": 80},
            {"上市": 139, "上櫃": 137},
            {"上市": 201, "上櫃": 198},
            {"上市": 263, "上櫃": 261},
        ]
        with patch.object(ma, "market_sessions", side_effect=state):
            with patch.object(ma, "run") as runner:
                result = ma.backfill_until(260, 3, 90)
                self.assertEqual(runner.call_count, 3)
                self.assertEqual(result["上櫃"], 261)

    def test_workflow_trigger_and_limits(self):
        text = (ROOT / ".github/workflows/backfill_v26.yml").read_text(encoding="utf-8")
        self.assertIn("backfill_ma240.py", text)
        self.assertIn("--batches 3 --days 90", text)
        self.assertIn("--target 260", text)
        self.assertIn("cancel-in-progress: false", text)


if __name__ == "__main__":
    unittest.main()
