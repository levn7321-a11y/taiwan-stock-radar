"""技術分析日／週／月線轉換。週線以週五結束，月線以月底結束。"""
import pandas as pd

PERIOD_OPTIONS = ["日線", "週線", "月線"]
LOOKBACK_OPTIONS = ["3個月", "6個月", "1年", "全部"]


def convert_price_period(df, frequency, *, index_col="date"):
    """接收日行情，回傳日／週／月 OHLCV 及對應 5/10/20/60/240 期均線。

    不以日線 MA 冒充週／月均線；最後一根可為尚未結束的週或月。
    """
    if frequency not in PERIOD_OPTIONS:
        raise ValueError(f"不支援的週期：{frequency}")
    frame = df.copy()
    if index_col in frame.columns:
        frame[index_col] = pd.to_datetime(frame[index_col], errors="coerce")
        frame = frame.dropna(subset=[index_col]).set_index(index_col)
    else:
        frame.index = pd.to_datetime(frame.index, errors="coerce")
    frame = frame.loc[frame.index.notna()].sort_index()
    for c in ("open", "high", "low", "close", "volume"):
        if c not in frame.columns:
            frame[c] = pd.NA
        frame[c] = pd.to_numeric(frame[c], errors="coerce")
    if frequency != "日線":
        rule = "W-FRI" if frequency == "週線" else "ME"
        frame = frame.resample(rule).agg({
            "open": "first", "high": "max", "low": "min",
            "close": "last", "volume": "sum",
        })
    frame = frame.dropna(subset=["close"]).copy()
    for n in (5, 10, 20, 60, 240):
        frame[f"MA{n}"] = frame["close"].rolling(n, min_periods=n).mean()
    frame["均量20"] = frame["volume"].rolling(20, min_periods=20).mean()
    frame.index.name = "date"
    return frame


def chart_tail_count(frequency, lookback, total):
    if lookback == "全部":
        return total
    periods = {"3個月": 3, "6個月": 6, "1年": 12}[lookback]
    if frequency == "日線":
        return int(periods * 22)
    if frequency == "週線":
        return int(periods * 4.5) + 1
    return periods
