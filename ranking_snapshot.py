"""Memory-safe ranking: SQLite computes rolling moving averages, returns one row per stock."""
import sqlite3
import pandas as pd

def snapshot_ranking(db):
    sql = """
    WITH rolling AS (
      SELECT date,market,code,name,close,volume,
        LAG(close) OVER (PARTITION BY market,code ORDER BY date) AS prior_close,
        AVG(close) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS ma5,
        COUNT(close) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 4 PRECEDING AND CURRENT ROW) AS n5,
        AVG(close) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS ma10,
        COUNT(close) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 9 PRECEDING AND CURRENT ROW) AS n10,
        AVG(close) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS ma20,
        COUNT(close) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS n20,
        AVG(close) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS ma60,
        COUNT(close) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 59 PRECEDING AND CURRENT ROW) AS n60,
        AVG(close) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS ma240,
        COUNT(close) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 239 PRECEDING AND CURRENT ROW) AS n240,
        AVG(volume) OVER (PARTITION BY market,code ORDER BY date ROWS BETWEEN 19 PRECEDING AND CURRENT ROW) AS avg_volume20,
        ROW_NUMBER() OVER (PARTITION BY market,code ORDER BY date DESC) AS rank_recent
      FROM daily
      WHERE market IN ('上市','上櫃') AND close > 0
    )
    SELECT date,market,code,name,close,volume,prior_close,
      CASE WHEN n5=5 THEN ma5 END AS MA5,
      CASE WHEN n10=10 THEN ma10 END AS MA10,
      CASE WHEN n20=20 THEN ma20 END AS MA20,
      CASE WHEN n60=60 THEN ma60 END AS MA60,
      CASE WHEN n240=240 THEN ma240 END AS MA240,
      CASE WHEN n20=20 THEN avg_volume20 END AS "均量20"
    FROM rolling WHERE rank_recent=1
    """
    with sqlite3.connect(db) as conn:
        result=pd.read_sql_query(sql,conn)
    if result.empty:
        return result
    result["date"]=pd.to_datetime(result["date"],errors="coerce")
    result["code"]=result["code"].astype(str).str.strip()
    result["漲跌幅%"]=(result["close"]/result["prior_close"]-1)*100
    result["量比"]=result["volume"]/result["均量20"].replace(0,float("nan"))
    result["多頭均線數"]=sum(
        (result["close"] > result[f"MA{n}"]).fillna(False).astype(int)
        for n in (5,10,20,60,240)
    )
    result["均線訊號"]=result.apply(
        lambda r: "站上月季線" if pd.notna(r["MA60"]) and r["close"]>r["MA20"] and r["close"]>r["MA60"]
        else "站上月線" if pd.notna(r["MA20"]) and r["close"]>r["MA20"] else "觀察", axis=1
    )
    return result
