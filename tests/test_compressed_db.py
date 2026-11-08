"""Verify complete sqlite compression preserves daily + institutional data."""
import gzip
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import runtime_db


class CompressedHistoryTests(unittest.TestCase):
    def test_restore_all_tables_and_rows(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)
            database=base/"twstock.sqlite3"
            archive=base/"twstock_full.sqlite3.gz"
            marker=base/".loaded"
            newdb=base/"source.db"
            with sqlite3.connect(newdb) as con:
                con.execute("CREATE TABLE daily(date TEXT,market TEXT,code TEXT,close REAL)")
                con.execute("CREATE TABLE institutional(date TEXT,code TEXT,foreign_net INTEGER)")
                con.execute("INSERT INTO daily VALUES ('2025-11-10','上市','2330',123)")
                con.execute("INSERT INTO institutional VALUES ('2025-11-10','2330',5000)")
            with newdb.open("rb") as src, gzip.open(archive,"wb") as dst:
                import shutil
                shutil.copyfileobj(src,dst)
            with patch.object(runtime_db,"ROOT",base),patch.object(runtime_db,"DB",database),patch.object(runtime_db,"ARCHIVE",archive),patch.object(runtime_db,"MARKER",marker):
                result=runtime_db.ensure_db()
                self.assertEqual(result,database)
                with sqlite3.connect(database) as con:
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM daily").fetchone()[0],1)
                    self.assertEqual(con.execute("SELECT COUNT(*) FROM institutional").fetchone()[0],1)
                self.assertEqual(runtime_db.ensure_db(),database)

    def test_uncompressed_fallback(self):
        with tempfile.TemporaryDirectory() as root:
            base=Path(root)
            with patch.object(runtime_db,"DB",base/"twstock.sqlite3"),patch.object(runtime_db,"ARCHIVE",base/"noarchive.gz"):
                self.assertEqual(runtime_db.ensure_db(),base/"twstock.sqlite3")


if __name__=="__main__":
    unittest.main()
