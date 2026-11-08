"""Publish large SQLite histories as gzip, restore automatically at Streamlit startup.

The original checked-in twstock.sqlite3 remains a fallback. The compressed
archive contains the entire database, including institutional and retry tables.
"""
import gzip
import os
from pathlib import Path
import shutil
import tempfile

ROOT = Path(__file__).resolve().parent
DB = ROOT / "twstock.sqlite3"
ARCHIVE = ROOT / "twstock_full.sqlite3.gz"
MARKER = ROOT / ".twstock_archive_loaded"


def ensure_db(force=False):
    """Use the complete compressed historical data if present and newer."""
    if not ARCHIVE.exists():
        return DB
    stamp = f"{ARCHIVE.stat().st_size}:{ARCHIVE.stat().st_mtime_ns}"
    if not force and DB.exists() and MARKER.exists() and MARKER.read_text() == stamp:
        return DB
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=ROOT, prefix=".twstock_restore_",
                                         suffix=".sqlite3", delete=False) as tmp:
            tmp_path = Path(tmp.name)
            with gzip.open(ARCHIVE, "rb") as compressed:
                shutil.copyfileobj(compressed, tmp, length=1024 * 1024)
        if tmp_path.stat().st_size < 1024:
            raise ValueError("歷史資料庫壓縮檔大小異常")
        # Verify complete decompression before replacing active DB.
        import sqlite3
        with sqlite3.connect(f"file:{tmp_path}?mode=ro", uri=True) as con:
            result = con.execute("PRAGMA quick_check").fetchone()
            if not result or result[0] != "ok":
                raise ValueError("解壓縮後 SQLite 完整性檢查失敗")
        os.replace(tmp_path, DB)
        tmp_path = None
        MARKER.write_text(stamp)
        return DB
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)
