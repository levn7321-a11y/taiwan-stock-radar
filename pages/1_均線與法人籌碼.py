import sqlite3
from pathlib import Path
import pandas as pd
import streamlit as st

st.set_page_config(page_title='均線與法人籌碼 | 台股突破雷達', layout='wide')
st.title('📈 台股 AI 突破雷達 V2.1')
st.caption('均線自動讀取既有 SQLite 股價資料｜法人資料可先匯入 CSV｜研究用途，非投資建議')
DB = Path(__file__).resolve().parents[1] / 'twstock.sqlite3'

@st.cache_data(ttl=300)
def load_prices(path, modified):
    with sqlite3.connect(path) as conn:
        return pd.read_sql_query('SELECT date, market, code, name, close FROM daily ORDER BY market, code, date', conn)

@st.cache_data(ttl=300)
def load_institutional_db(path, modified):
    with sqlite3.connect(path) as conn:
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'institutional' not in tables:
            return None
        return pd.read_sql_query('SELECT * FROM institutional', conn)

def normalize_institutional(df):
    required = {'date', 'market', 'code', 'name', 'foreign_net', 'trust_net'}
    missing = required - set(df.columns)
    if missing:
        raise ValueError('缺少欄位：' + ', '.join(sorted(missing)))
    df = df.copy()
    df['date'] = pd.to_datetime(df['date'], errors='coerce')
    df['code'] = df['code'].astype(str).str.strip().str.replace(r'\.0$', '', regex=True)
    for col in ('foreign_net', 'trust_net'):
        df[col] = pd.to_numeric(df[col].astype(str).str.replace(',', '', regex=False), errors='coerce')
    return df.dropna(subset=['date'])

tab1, tab2 = st.tabs(['📊 均線分析', '🏦 法人排行榜'])
with tab1:
    st.subheader('5／10／20／60／240 日均線')
    if not DB.exists():
        st.warning('找不到 twstock.sqlite3。請先執行 GitHub Actions 的每日更新或歷史回補。')
    else:
        try:
            prices = load_prices(str(DB), DB.stat().st_mtime_ns)
            if prices.empty:
                st.info('資料庫目前沒有股價資料。')
            else:
                prices['date'] = pd.to_datetime(prices['date'], errors='coerce')
                prices['close'] = pd.to_numeric(prices['close'], errors='coerce')
                prices['code'] = prices['code'].astype(str)
                prices = prices.dropna(subset=['date', 'close']).sort_values(['market', 'code', 'date'])
                prices = prices.drop_duplicates(['market', 'code', 'date'], keep='last')
                market = st.selectbox('市場', ['上市＋上櫃', '上市', '上櫃'], key='ma_market')
                if market != '上市＋上櫃':
                    prices = prices[prices['market'] == market]
                options = prices[['market', 'code', 'name']].drop_duplicates().sort_values(['market', 'code'])
                if options.empty:
                    st.info('目前所選市場沒有資料。')
                else:
                    options['label'] = options['code'] + ' ' + options['name'] + '（' + options['market'] + '）'
                    chosen = st.selectbox('選擇股票', options['label'].tolist())
                    selected = options.loc[options['label'] == chosen].iloc[0]
                    stock = prices[(prices['market'] == selected['market']) & (prices['code'] == selected['code'])].copy()
                    stock = stock.sort_values('date').set_index('date')
                    for n in (5, 10, 20, 60, 240):
                        stock[f'MA{n}'] = stock['close'].rolling(n, min_periods=n).mean()
                    st.caption(f'最新行情：{stock.index.max().date()}｜累積 {len(stock)} 個交易日')
                    st.line_chart(stock[['close', 'MA5', 'MA10', 'MA20', 'MA60', 'MA240']].tail(120))
                    st.dataframe(stock[['close', 'MA5', 'MA10', 'MA20', 'MA60', 'MA240']].tail(15).sort_index(ascending=False), use_container_width=True)
                    if len(stock) < 240:
                        st.warning(f'目前只有 {len(stock)} 個交易日，240 日年線尚無法計算。')
        except Exception as exc:
            st.error(f'讀取股價資料失敗：{exc}')

with tab2:
    st.subheader('外資／投信每日買賣超 TOP 15')
    st.caption('優先讀取資料庫 institutional 資料表；若尚未建立，可匯入整理好的 CSV。買賣超單位依資料來源而定，請先確認單位一致。')
    uploaded = st.file_uploader('匯入法人 CSV（選用）', type=['csv'], key='inst_csv_v21')
    institutional = None
    if uploaded is not None:
        try:
            institutional = normalize_institutional(pd.read_csv(uploaded, dtype={'code': str}))
        except Exception as exc:
            st.error(f'CSV 讀取失敗：{exc}')
    elif DB.exists():
        try:
            institutional = load_institutional_db(str(DB), DB.stat().st_mtime_ns)
            if institutional is not None:
                institutional = normalize_institutional(institutional)
        except Exception as exc:
            st.error(f'法人資料庫讀取失敗：{exc}')
    if institutional is None or institutional.empty:
        st.info('尚無法人資料。請先匯入包含 date、market、code、name、foreign_net、trust_net 的 CSV；自動法人更新仍需另外接入。')
    else:
        dates = sorted(institutional['date'].dt.date.unique(), reverse=True)
        chosen_date = st.selectbox('資料日期', dates)
        market = st.selectbox('市場', ['上市＋上櫃', '上市', '上櫃'], key='inst_market')
        data = institutional[institutional['date'].dt.date == chosen_date].copy()
        if market != '上市＋上櫃':
            data = data[data['market'] == market]
        for col, title in [('foreign_net', '外資'), ('trust_net', '投信')]:
            st.markdown(f'#### {title}買賣超')
            left, right = st.columns(2)
            cols = ['market', 'code', 'name', col]
            with left:
                st.write('買超前 15 名')
                st.dataframe(data[data[col] > 0].nlargest(15, col)[cols], hide_index=True, use_container_width=True)
            with right:
                st.write('賣超前 15 名')
                st.dataframe(data[data[col] < 0].nsmallest(15, col)[cols], hide_index=True, use_container_width=True)

