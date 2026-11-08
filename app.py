import io
import re
import sqlite3
from datetime import datetime, date, timedelta
from pathlib import Path
import pandas as pd
import requests
import streamlit as st

from storage import init_db, save, fetch_latest, FIELDS
from history import backfill, day
from top_nav import show_top_nav
from market_indices import show_market_indices


def scan(df, min_turnover=5000000, vol_multiple=1.8, breakout_days=20):
    out = []
    for (market, code), g in df.groupby(['market', 'code']):
        g = g.sort_values('date').drop_duplicates('date').copy()
        if len(g) < max(61, breakout_days + 1):
            continue
        prev = g.iloc[:-1]
        now = g.iloc[-1]
        if now.close <= 0:
            continue
        avgvol = prev.volume.tail(20).mean()
        if avgvol <= 0:
            continue
        volratio = now.volume / avgvol
        # Historical OHLC is raw/unadjusted. Corporate actions may distort these signals.
        high20 = prev.high.tail(20).max()
        high60 = prev.high.tail(60).max()
        ma20 = prev.close.tail(20).mean()
        ma60 = prev.close.tail(60).mean()
        priorclose = prev.close.iloc[-1]
        change = (now.close / priorclose - 1) * 100 if priorclose > 0 else 0
        turnover = now.close * now.volume
        if turnover < min_turnover:
            continue
        breakout20 = now.close > high20
        breakout60 = now.close > high60
        strongclose = (now.close - now.low) / (now.high - now.low) if now.high > now.low else .5
        extended = (now.close / ma20 - 1) * 100 if ma20 > 0 else 0
        score = (30 if breakout60 else 22 if breakout20 else 0)
        score += min(25, max(0, (volratio - 1) * 12))
        score += 15 if now.close > ma20 > ma60 else 8 if now.close > ma20 else 0
        score += 15 if strongclose >= .8 and change > 0 else 8 if strongclose >= .6 and change > 0 else 0
        score += 10 if change >= 3 else 5 if change > 0 else 0
        score += 5 if turnover >= 30000000 else 0
        risk = []
        if extended > 15:
            risk.append('20日均線乖離偏高')
        if change >= 9:
            risk.append('接近漲停，追價風險')
        if volratio > 5:
            risk.append('極端爆量，留意反轉')
        if now.close < ma20:
            risk.append('跌破20日均線')
        if not (breakout20 or volratio >= vol_multiple):
            continue
        out.append({
            '日期': now.date, '市場': market, '代號': code, '名稱': now['name'],
            '收盤價': round(now.close, 2), '漲跌幅%': round(change, 2),
            '量比': round(volratio, 2), '成交金額(萬)': round(turnover / 10000, 1),
            '突破20日': breakout20, '突破60日': breakout60,
            '20日均線': round(ma20, 2), '60日均線': round(ma60, 2),
            '分數': round(min(100, score), 1),
            '風險提示': '、'.join(risk) or '無額外規則警示'
        })
    return pd.DataFrame(out).sort_values(['分數', '量比'], ascending=False) if out else pd.DataFrame()


st.set_page_config(page_title='台股 AI 突破雷達 V2.0', layout='wide', initial_sidebar_state='collapsed')
show_top_nav(restore_db=False)

show_market_indices()
st.title('📈 台股 AI 突破雷達 V2.0')
st.caption('上市＋上櫃｜日線突破、爆量、短線異動｜研究用途，非投資建議｜非盤中即時報價')
init_db()
with st.sidebar:
    st.header('資料與設定')
    if st.button('抓取官方最新收盤行情', type='primary', use_container_width=True):
        info = fetch_latest()
        if info['markets']:
            st.success(str(info['markets']))
        if info['errors']:
            st.error('；'.join(info['errors']))
    with st.expander('歷史資料回補（首次使用）'):
        st.caption('從官方按交易日抓取，建議首次選 100～120 天；可能耗時數分鐘，官方網站若封鎖請稍後重試。')
        lookback = st.number_input('回補日曆天數', min_value=90, max_value=365, value=120, step=10)
        market_choice = st.selectbox('回補市場', ['both', '上市', '上櫃'], format_func=lambda v: '上市＋上櫃' if v == 'both' else v)
        if st.button('開始回補歷史行情'):
            bar = st.progress(0, text='正在連線官方資料源')
            total = max(1, len(pd.date_range(date.today() - timedelta(days=int(lookback)), date.today(), freq='B'))) * (2 if market_choice == 'both' else 1)
            counter = [0]
            def report(d, m, r):
                counter[0] += 1
                bar.progress(min(1, counter[0] / total), text=f'{d} {m}｜已寫入 {r["saved"]} 筆')
            result = backfill(save, date.today() - timedelta(days=int(lookback)), date.today(), market_choice, progress=report)
            st.write(result)
            if result['errors']:
                st.error('部分日期回補失敗，請重新執行補齊；詳見錯誤列表。')
    st.markdown('**匯入歷史行情 CSV**')
    uploaded = st.file_uploader('欄位 date,market,code,name,open,high,low,close,volume', type='csv')
    if uploaded and st.button('驗證並匯入 CSV'):
        try:
            h = pd.read_csv(uploaded, dtype={'code': str, 'date': str})
            missing = set(FIELDS) - set(h.columns)
            if missing:
                raise ValueError(f'缺少欄位：{missing}')
            h = h[FIELDS].copy()
            h['date'] = h.date.map(day)
            for k in ['open', 'high', 'low', 'close', 'volume']:
                h[k] = pd.to_numeric(h[k], errors='raise')
            if not h.market.isin(['上市', '上櫃']).all():
                raise ValueError('market 必須是上市或上櫃')
            if not h.code.astype(str).str.fullmatch(r'\d{4}').all():
                raise ValueError('code 必須是4位數普通股代碼')
            if h[['open', 'high', 'low', 'close']].le(0).any().any() or h.volume.lt(0).any():
                raise ValueError('價格需大於0，成交股數不可為負')
            save(h)
            st.success(f'匯入 {len(h)} 筆')
        except Exception as e:
            st.error(f'匯入失敗：{e}')
    min_turnover = st.number_input('最低日成交金額（萬元）', min_value=0, value=3000, step=500)
    vol_multiple = st.slider('爆量門檻（20日均量倍數）', 1.0, 5.0, 1.8, .1)
    st.info('首次只抓最新一天，需累積至少61個交易日，或匯入歷史資料，才能計算完整突破訊號。')

# Use only the latest 100 MARKET dates for the home scanner. The full 240+/260-day
# history remains stored for individual MA240 analysis; loading it all into the
# landing page previously caused large memory spikes on Streamlit Cloud.
@st.cache_data(ttl=900, max_entries=2)
def load_home_scan(db_stamp):
    from storage import DB
    with sqlite3.connect(DB) as conn:
        return pd.read_sql_query("""
            SELECT date,market,code,name,open,high,low,close,volume FROM daily
            WHERE date >= (
                SELECT MIN(date) FROM (
                    SELECT DISTINCT date FROM daily ORDER BY date DESC LIMIT 100
                )
            )
            ORDER BY market,code,date
        """, conn)

st.subheader("📡 短線突破掃描")
if st.button("🔍 開始掃描行情", type="primary", key="home_scan_start"):
    st.session_state["home_scan_enabled"] = True
if st.session_state.get("home_scan_enabled", False):
    from storage import DB as LOCAL_DB
    df = load_home_scan(LOCAL_DB.stat().st_mtime_ns)
    a, b, c = st.columns(3)
    a.metric('已存股票數', df[['market', 'code']].drop_duplicates().shape[0] if len(df) else 0)
    b.metric('已存交易日期數', df.date.nunique() if len(df) else 0)
    c.metric('最新資料日期', df.date.max() if len(df) else '尚無')
    if df.empty:
        st.warning('尚無資料。請先按左側「抓取官方最新收盤行情」，或匯入歷史 CSV。')
    else:
        latest = df.date.max()
        counts = df.groupby(['market', 'code']).date.nunique()
        eligible = int((counts >= 61).sum())
        st.caption(f'可計算完整60日歷史訊號的股票：{eligible} 檔。最新收盤日：{latest}。不同市場若日期不一致，請留意資料新鮮度。')
        if eligible == 0:
            st.warning('歷史資料不足：目前不顯示突破排行榜，避免把單日上漲誤認為突破。')
        else:
            result = scan(df, min_turnover * 10000, vol_multiple)
            if not result.empty:
                result = result[result['日期'] == latest]
            if result.empty:
                st.info('目前沒有符合篩選條件的股票。')
            else:
                market_filter = st.multiselect('市場', ['上市', '上櫃'], default=['上市', '上櫃'])
                only_breakout = st.checkbox('只看20日／60日突破', value=False)
                result = result[result['市場'].isin(market_filter)]
                if only_breakout:
                    result = result[result['突破20日'] | result['突破60日']]
                st.subheader(f'異動排行榜（{len(result)} 檔）')
                st.dataframe(result, use_container_width=True, hide_index=True)
                st.download_button('下載排行榜 CSV', result.to_csv(index=False).encode('utf-8-sig'), 'breakout_rank.csv', 'text/csv')
                if len(result):
                    code = st.selectbox('個股走勢', result['代號'].tolist(), format_func=lambda x: f"{x} {result.loc[result['代號'] == x, '名稱'].iloc[0]}")
                    r = result[result['代號'] == code].iloc[0]
                    g = df[(df.code == code) & (df.market == r['市場'])].sort_values('date').tail(100)
                    st.line_chart(g.set_index('date')[['close']])
                    st.write(f"量比 {r['量比']} 倍；20日突破：{'是' if r['突破20日'] else '否'}；60日突破：{'是' if r['突破60日'] else '否'}；風險：{r['風險提示']}")
else:
    st.info("首頁已載入。需要查看突破、量能及異動排行時，請按「開始掃描行情」；個股 MA240 仍可由上方選單查看完整歷史。")
st.divider()

