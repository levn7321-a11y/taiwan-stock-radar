"""日／週／月線共用 OHLCV 週期聚合。

資料依交易日期排序：週線以星期五為週結束，月線以曆月月底為結束。
當期尚未完結的週／月也會呈現為截至最新交易日的未完成 K 棒。
"""
import pandas as pd

PERIODS = ("日線", "週線", "月線")


def resample_price_timeframe(frame, period):
    """輸入包含 close、volume 及日期 index 或 date 欄位；回傳 date index 的聚合資料。"""
    if period not in PERIODS:
        raise ValueError(f"不支援的週期：{period}")
    if frame.empty:
        return frame.copy()

    price = frame.copy()
    if "date" in price.columns:
        price["date"] = pd.to_datetime(price["date"], errors="coerce")
        price = price.set_index("date")
    else:
        price.index = pd.to_datetime(price.index, errors="coerce")
    price = price[price.index.notna()].sort_index()
    price = price[~price.index.duplicated(keep="last")]
    if period == "日線":
        return price

    agg = {"close": "last", "volume": "sum"}
    for col, op in (("open", "first"), ("high", "max"), ("low", "min")):
        if col in price.columns:
            agg[col] = op
    grouped = price.resample("W-FRI" if period == "週線" else "ME").agg(agg)
    return grouped.dropna(subset=["close"])


def add_period_moving_averages(frame, periods=(5, 10, 20, 60, 240)):
    """均線以選定 K 線週期計算，週線 MA20 代表 20 週而非 20 日。"""
    result = frame.copy()
    for n in periods:
        result[f"MA{n}"] = result["close"].rolling(n, min_periods=n).mean()
    if "volume" in result:
        result["均量20"] = result["volume"].rolling(20, min_periods=20).mean()
    return result
