"""共用台股 K 線及下方可切換指標：量能、KD、法人與外資。"""
import altair as alt
import pandas as pd

PANEL_OPTIONS = ["成交量", "KD線", "三大法人買賣超", "外資買賣超"]
RED = "#f04b58"       # 台股慣例：紅漲
GREEN = "#17b978"     # 台股慣例：綠跌
FLAT = "#9ca3af"

def calculate_kd(bars, n=9):
    """標準 RSV(9)、K/D(3,3) 平滑，初值 50；短於 9 根不顯示 KD。"""
    result = bars.copy()
    low = result["low"].rolling(n, min_periods=n).min()
    high = result["high"].rolling(n, min_periods=n).max()
    span = (high-low)
    rsv = ((result["close"]-low) / span.where(span.ne(0)) * 100).where(span.ne(0), 50)
    kval = 50.0
    dval = 50.0
    ks, ds = [], []
    for item in rsv:
        if pd.isna(item):
            ks.append(float("nan"))
            ds.append(float("nan"))
            continue
        kval = (2*kval + float(item))/3
        dval = (2*dval + kval)/3
        ks.append(kval)
        ds.append(dval)
    result["K"] = ks
    result["D"] = ds
    return result


def aggregate_institutional(inst, calendar, frequency):
    """按交易日稽核法人資料，再依日/週/月合計；缺任一日不虛構零值。"""
    frame = pd.DataFrame(index=calendar)
    cols = ["foreign_net", "trust_net", "dealer_net"]
    for col in cols:
        frame[col] = pd.NA
    if not inst.empty:
        source = inst.copy()
        source["date"] = pd.to_datetime(source["date"], errors="coerce").dt.normalize()
        source = source.dropna(subset=["date"]).drop_duplicates("date", keep="last").set_index("date")
        for col in cols:
            if col in source:
                frame[col] = pd.to_numeric(source[col], errors="coerce").reindex(calendar)
    frame = frame.apply(pd.to_numeric, errors="coerce")
    if frequency != "日線":
        rule = "W-FRI" if frequency == "週線" else "M"
        # 必須每一個市場交易日均存在，否則該根法人柱顯示缺資料。
        totals = frame.resample(rule).sum(min_count=1)
        available = frame.resample(rule).count()
        expected = frame.resample(rule).size()
        frame = totals.where(available.eq(expected, axis=0))
    frame["三大法人買賣超"] = frame[cols].sum(axis=1, min_count=3)
    frame["外資買賣超"] = frame["foreign_net"]
    return frame / 1000.0


def chart_view(bars, panel, frequency="日線", inst=None, calendar=None):
    """建立 K 棒、均線與可切換下方副圖；法人單位為張。"""
    if bars.empty:
        return None, "查無價格行情"
    prepared = calculate_kd(bars)
    if prepared[["open","high","low","close"]].isna().any().any():
        return None, "部分開高低收資料缺漏，無法繪製完整 K 棒"
    df = prepared.reset_index().copy()
    df["日期"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["漲跌"] = df["close"]-df["open"]
    df["漲跌幅%"] = (df["close"]/df["open"]-1)*100
    df["方向"] = df["漲跌"].map(lambda x: "上漲" if x>0 else "下跌" if x<0 else "持平")
    df["棒頂"] = df[["open","close"]].max(axis=1)
    df["棒底"] = df[["open","close"]].min(axis=1)
    color = alt.Color("方向:N", scale=alt.Scale(domain=["上漲","下跌","持平"],
                  range=[RED,GREEN,FLAT]),legend=None)
    base = alt.Chart(df)
    xt = alt.X("日期:O", title=None, axis=alt.Axis(labelAngle=-60, labelLimit=76, labelOverlap=True))
    tooltips = [alt.Tooltip("日期:N"),alt.Tooltip("open:Q",title="開盤",format=",.2f"),
                alt.Tooltip("high:Q",title="最高",format=",.2f"),
                alt.Tooltip("low:Q",title="最低",format=",.2f"),
                alt.Tooltip("close:Q",title="收盤",format=",.2f"),
                alt.Tooltip("漲跌幅%:Q",title="開收漲跌%",format="+.2f"),
                alt.Tooltip("volume:Q",title="成交股數",format=",.0f")]
    wick = base.mark_rule(strokeWidth=1.25).encode(x=xt, y=alt.Y("low:Q",scale=alt.Scale(zero=False),title="股價"),
                  y2="high:Q",color=color,tooltip=tooltips)
    body = base.mark_bar(size=9).encode(x=xt,y="棒底:Q",y2="棒頂:Q",color=color,tooltip=tooltips)
    layers=[wick,body]
    ma_colors = {"MA5":"#e4c334","MA10":"#54d1ee","MA20":"#b57cf2","MA60":"#55c2a9","MA240":"#ee8fa7"}
    for col,hue in ma_colors.items():
        if col in df and df[col].notna().any():
            layers.append(base.mark_line(strokeWidth=1.6,color=hue).encode(x=xt,
                y=alt.Y(f"{col}:Q"),tooltip=[alt.Tooltip("日期:N"),alt.Tooltip(f"{col}:Q",format=",.2f")]))
    # 明確標示目前視圖範圍內的最高價與最低價，兩者各一個標籤。
    max_bar = df.loc[[df["high"].idxmax()]]
    min_bar = df.loc[[df["low"].idxmin()]]
    labels_high = alt.Chart(max_bar).mark_text(
        dy=-12, fontSize=12, fontWeight="bold", color="#d94452"
    ).encode(x=xt, y="high:Q", text=alt.Text("high:Q",format=",.2f"),
             tooltip=[alt.Tooltip("日期:N"),alt.Tooltip("high:Q",title="區間最高",format=",.2f")])
    labels_low = alt.Chart(min_bar).mark_text(
        dy=14, fontSize=12, fontWeight="bold", color="#078b60"
    ).encode(x=xt, y="low:Q", text=alt.Text("low:Q",format=",.2f"),
             tooltip=[alt.Tooltip("日期:N"),alt.Tooltip("low:Q",title="區間最低",format=",.2f")])
    layers.extend([labels_high, labels_low])
    primary=alt.layer(*layers).properties(height=355,title="紅漲綠跌｜日／週／月 K 線與移動平均線")
    warning = ""
    if panel=="成交量":
        volumes = base.mark_bar(size=10).encode(x=xt,
            y=alt.Y("volume:Q",title="成交量（股）"),color=color,
            tooltip=[alt.Tooltip("日期:N"),alt.Tooltip("volume:Q",format=",.0f")])
        numbers = alt.Chart(df.tail(7)).mark_text(dy=-9,fontSize=10).encode(
            x=xt,y="volume:Q",text=alt.Text("volume:Q",format=",.0f"),color=color)
        bottom = alt.layer(volumes,numbers)
    elif panel=="KD線":
        valid=df.dropna(subset=["K","D"])
        if valid.empty:
            warning="KD 至少需要 9 根有效 K 棒，目前資料不足"
            bottom=base.mark_point(opacity=0).encode(x=xt,y=alt.Y("K:Q",title="KD"))
        else:
            k=alt.Chart(valid).mark_line(strokeWidth=2,color="#e6c13f").encode(
                x=xt,y=alt.Y("K:Q",scale=alt.Scale(domain=[0,100]),title="KD (0–100)"),
                tooltip=[alt.Tooltip("日期:N"),alt.Tooltip("K:Q",format=".1f")])
            d=alt.Chart(valid).mark_line(strokeWidth=2,color="#67b7ef").encode(
                x=xt,y="D:Q",tooltip=[alt.Tooltip("日期:N"),alt.Tooltip("D:Q",format=".1f")])
            bottom=alt.layer(k,d)
    else:
        if inst is None or calendar is None or len(calendar)==0:
            warning="目前沒有法人資料，無法顯示買賣超"
            bottom=base.mark_point(opacity=0).encode(x=xt,y=alt.Y("volume:Q",title="缺法人資料"))
        else:
            values=aggregate_institutional(inst,pd.DatetimeIndex(calendar),frequency)
            key=panel
            joined=df[["日期","date"]].copy()
            joined[key]=values[key].reindex(pd.DatetimeIndex(joined["date"])).to_numpy()
            joined["方向"]=joined[key].map(lambda v: "買超" if pd.notna(v) and v>0 else "賣超" if pd.notna(v) and v<0 else "持平")
            if joined[key].notna().sum()==0:
                warning="所選期間無完整法人紀錄，缺資料不視為 0"
            direction_color = alt.Color("方向:N",scale=alt.Scale(domain=["買超","賣超","持平"],
                               range=[RED,GREEN,FLAT]),legend=None)
            bars = alt.Chart(joined).mark_bar(size=10).encode(
                x=xt,y=alt.Y(f"{key}:Q",title=f"{key}（張）"),
                color=direction_color,
                tooltip=[alt.Tooltip("日期:N"),alt.Tooltip(f"{key}:Q",format="+,.0f")])
            label_data = joined.dropna(subset=[key]).tail(7)
            numbers = alt.Chart(label_data).mark_text(dy=-9,fontSize=10).encode(
                x=xt,y=alt.Y(f"{key}:Q"),
                text=alt.Text(f"{key}:Q",format="+,.0f"),color=direction_color)
            bottom = alt.layer(bars,numbers)
    combined=alt.vconcat(primary,bottom.properties(height=145,title=panel),
                         spacing=5).resolve_scale(x="shared",y="independent")
    return combined, warning
