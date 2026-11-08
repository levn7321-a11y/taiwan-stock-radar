"""Moving average computations for a normalized OHLCV DataFrame."""
import pandas as pd

WINDOWS=(5,10,20,60,240)
def add_ma(df):
    """Input columns: date,market,code,name,close. Output retains original columns."""
    d=df.copy()
    if d.empty:return d
    d['date']=pd.to_datetime(d['date'],errors='coerce')
    d['close']=pd.to_numeric(d['close'],errors='coerce')
    d=d.dropna(subset=['date','close']).sort_values(['market','code','date'])
    for n in WINDOWS:
        d[f'MA{n}']=d.groupby(['market','code'])['close'].transform(lambda s:s.rolling(n,min_periods=n).mean())
    d['站上月線']=(d['close']>d['MA20']) & d['MA20'].notna()
    d['均線多頭排列']=(d['MA5']>d['MA10'])&(d['MA10']>d['MA20'])&(d['MA20']>d['MA60'])&(d['MA60']>d['MA240'])
    prev_close=d.groupby(['market','code'])['close'].shift()
    prev_ma20=d.groupby(['market','code'])['MA20'].shift()
    d['突破月線']=(prev_close<=prev_ma20)&(d['close']>d['MA20'])
    prev_ma5=d.groupby(['market','code'])['MA5'].shift()
    prev_ma10=d.groupby(['market','code'])['MA10'].shift()
    d['五日十日黃金交叉']=(prev_ma5<=prev_ma10)&(d['MA5']>d['MA10'])
    return d
