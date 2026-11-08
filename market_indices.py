"""首頁收盤指數摘要。只顯示官方來源實際日期及指數值。"""
import requests
import streamlit as st

TWSE_URL = "https://openapi.twse.com.tw/v1/exchangeReport/MI_INDEX"
TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainborad_highlight"


def number(value):
    try:
        return float(str(value).replace(",", "").replace("+", "").strip())
    except (ValueError, TypeError):
        return None


def roc_date(raw):
    s = str(raw).strip().replace("/", "")
    if len(s) == 7 and s.isdigit():
        return f"{int(s[:3])+1911:04d}-{s[3:5]}-{s[5:7]}"
    if len(s) == 8 and s.isdigit():
        return f"{s[:4]}-{s[4:6]}-{s[6:]}"
    return str(raw) if raw else "日期未提供"


def parse_twse(rows):
    result = {}
    if not isinstance(rows, list):
        return result
    keys = {"發行量加權股價指數": "大盤加權指數",
            "金融保險類指數": "金融保險類股指數"}
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = keys.get(item.get("指數"))
        value = number(item.get("收盤指數"))
        if name and value is not None:
            sign = -1 if str(item.get("漲跌", "")).strip() == "-" else 1
            move = number(item.get("漲跌點數"))
            result[name] = {
                "date": roc_date(item.get("日期")),
                "close": value,
                "change": round(sign * move, 2) if move is not None else None,
                "source": "臺灣證券交易所",
            }
    return result


def parse_tpex(rows):
    if not isinstance(rows, list):
        return None
    for item in rows:
        if not isinstance(item, dict):
            continue
        close = number(item.get("收市指數"))
        if close is None:
            continue
        change = number(item.get("指數漲跌"))
        return {"date": roc_date(item.get("資料日期")),
                "close": close, "change": change, "source": "證券櫃檯買賣中心"}
    return None


@st.cache_data(ttl=900, show_spinner=False)
def fetch_indices():
    result = {}
    for url, decoder in ((TWSE_URL, parse_twse), (TPEX_URL, parse_tpex)):
        try:
            resp = requests.get(url, timeout=10,
                                headers={"User-Agent": "Mozilla/5.0", "Accept":"application/json"})
            resp.raise_for_status()
            rows = resp.json()
            parsed = decoder(rows)
            if decoder is parse_tpex:
                if parsed:
                    result["櫃買指數"] = parsed
            else:
                result.update(parsed)
        except (requests.RequestException, ValueError, TypeError):
            continue
    return result


def show_market_indices():
    st.subheader("📊 台股三大市場指數")
    values = fetch_indices()
    cols = st.columns(3)
    for col, name in zip(cols, ("大盤加權指數", "櫃買指數", "金融保險類股指數")):
        with col:
            item = values.get(name)
            if item:
                delta = item["change"]
                st.metric(name, f'{item["close"]:,.2f}',
                          delta=f'{delta:+,.2f} 點' if delta is not None else None,
                          delta_color="normal")
                st.caption(f'{item["date"]} 收盤｜{item["source"]}')
            else:
                st.metric(name, "暫無資料")
                st.caption("官方指數資料尚未取得")
    st.caption("官方最近公布之收盤資訊，非盤中即時指數。")
