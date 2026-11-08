"""共用上方浮動導覽與黑／白模式。使用 Streamlit 原生元件以保留跨頁 session_state。"""
import streamlit as st
from runtime_db import ensure_db
import sqlite3
from pathlib import Path

# 六個主選單，每個都可以點擊開啟浮動式下拉選擇。
MENUS = (
    ("🏠 市場掃描", (("市場掃描首頁", "app.py"), ("行情／均線排行榜", "pages/1_均線與法人籌碼.py"))),
    ("📊 行情與均線", (("行情與均線總覽", "pages/1_均線與法人籌碼.py"), ("個股技術分析", "pages/2_個股技術分析.py"))),
    ("🏦 法人買賣超", (("法人買／賣超前 15 名", "pages/4_法人買賣超排行.py"), ("法人籌碼總覽", "pages/1_均線與法人籌碼.py"))),
    ("⭐ 自選個股", (("我的自選個股", "pages/3_自選個股.py"), ("選股排行榜", "pages/1_均線與法人籌碼.py"))),
    ("🏆 近期高分", (("近期高分股票", "pages/5_近期高分股票.py"), ("短線突破雷達", "app.py"))),
    ("📈 個股分析", (("個股技術分析", "pages/2_個股技術分析.py"), ("自選個股走勢", "pages/3_自選個股.py"))),
)


def _theme_css(light):
    bg = "#f8fafc" if light else "#0c1422"
    panel = "#ffffff" if light else "#162334"
    text = "#192638" if light else "#eff5fd"
    muted = "#5b6a80" if light else "#9fb2c9"
    border = "#dce4ed" if light else "#2c4057"
    hover = "#e8f3fe" if light else "#20384f"
    accent = "#1279c4" if light else "#5cb5fa"
    # DataGrid 由 Streamlit 自己繪製，此處以容器及字色為主；原生介面仍會受使用者瀏覽器設定影響。
    return f"""
    <style>
    :root {{
      --background-color: {bg};
      --secondary-background-color: {panel};
      --text-color: {text};
      --primary-color: {accent};
    }}
    html, body, [data-testid="stApp"], [data-testid="stAppViewContainer"],
    [data-testid="stMain"], [data-testid="stHeader"],
    [data-testid="stSidebar"] {{
      background-color: {bg} !important;
      color: {text} !important;
    }}
    [data-testid="stApp"] p, [data-testid="stApp"] h1,
    [data-testid="stApp"] h2, [data-testid="stApp"] h3,
    [data-testid="stApp"] label,
    [data-testid="stSidebar"] p, [data-testid="stSidebar"] label {{
      color: {text};
    }}
    [data-testid="stApp"] small, [data-testid="stApp"] .stCaption {{
      color: {muted} !important;
    }}
    [data-testid="stMetric"], .market-header, .stock-table-wrap {{
      background: {panel} !important;
      border-color: {border} !important;
    }}
    .market-header b, .market-header small {{
      color: {text} !important;
    }}
    .stock-table th {{
      background: {hover} !important;
      color: {text} !important;
    }}
    .stock-table td {{
      background: {panel} !important;
      color: {text} !important;
      border-color: {border} !important;
    }}
    [data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stMetric"] label {{
      color: {text} !important;
    }}
    .st-key-radar_top_nav {{
      position: relative;
      top: auto;
      z-index: 999;
      background: {panel};
      border: 1px solid {border};
      border-radius: 12px;
      padding: 18px 14px 12px;
      margin-top: 24px;
      margin-bottom: 16px;
      overflow: visible !important;
      box-shadow: 0 8px 25px rgba(5, 15, 35, .10);
    }}
    .st-key-radar_top_nav [data-testid="stPopover"] button {{
      min-height: 2.75rem !important;
      line-height: 1.45 !important;
      background: transparent !important;
      color: {text} !important;
      border: none !important;
      border-radius: 5px !important;
      font-weight: 650;
      white-space: nowrap;
    }}
    .st-key-radar_top_nav [data-testid="stPopover"] button:hover {{
      background: {hover} !important;
      color: {accent} !important;
    }}
    .st-key-radar_top_nav [data-testid="stPopover"] button * {{
      color: {text} !important;
    }}
    .st-key-radar_top_nav [data-testid="stToggle"] {{
      margin-top: 4px;
    }}
    .st-key-radar_top_nav [data-testid="stToggle"] label {{
      color: {text} !important;
      white-space: nowrap;
    }}
    [data-testid="stPopoverBody"] *,
    [data-testid="stPopoverBody"] a {{
      color: {text} !important;
    }}
    /* Streamlit segmented controls: prevent white unselected tabs with invisible labels. */
    [data-testid="stSegmentedControl"] button,
    [data-testid="stButtonGroup"] button,
    [data-testid="stButtonGroup"] [role="radio"],
    [data-testid="stSegmentedControl"] [role="radio"],
    [data-testid="stSegmentedControl"] [role="button"] {{
      background: {panel} !important;
      color: {text} !important;
      border-color: {border} !important;
    }}
    [data-testid="stSegmentedControl"] button *,
    [data-testid="stButtonGroup"] button *,
    [data-testid="stButtonGroup"] [role="radio"] *,
    [data-testid="stSegmentedControl"] [role="radio"] * {{
      color: {text} !important;
      opacity: 1 !important;
    }}
    [data-testid="stSegmentedControl"] button[aria-checked="true"],
    [data-testid="stButtonGroup"] button[aria-checked="true"],
    [data-testid="stButtonGroup"] button[aria-pressed="true"],
    [data-testid="stSegmentedControl"] button[aria-pressed="true"],
    [data-testid="stSegmentedControl"] [data-state="checked"] {{
      background: {hover} !important;
      outline: 2px solid {accent} !important;
    }}
    [data-testid="stRadio"] label *,
    [data-testid="stCheckbox"] label *,
    [data-testid="stDataFrame"] * {{
      opacity: 1;
    }}
    /* The historical stock dashboard ships fixed dark styling; override it for both themes. */
    [data-testid="stApp"] .market-header,
    [data-testid="stApp"] div[data-testid="stMetric"],
    [data-testid="stApp"] .stock-table-wrap {{
      background: {panel} !important;
      border-color: {border} !important;
    }}
    [data-testid="stApp"] .market-header b,
    [data-testid="stApp"] .market-header small,
    [data-testid="stApp"] div[data-testid="stMetric"] label,
    [data-testid="stApp"] div[data-testid="stMetric"] [data-testid="stMetricValue"],
    [data-testid="stApp"] .stock-table td {{
      color: {text} !important;
    }}
    [data-testid="stApp"] .stock-table th {{
      background: {hover} !important;
      color: {text} !important;
    }}
    [data-testid="stApp"] .stock-table td {{
      background: {panel} !important;
      border-color: {border} !important;
    }}
    [data-testid="stPopoverBody"] {{
      border: 1px solid {border};
      background: {panel};
      box-shadow: 0 12px 28px rgba(0,0,0,.22);
    }}
    </style>
    """


def _save_theme():
    # Widget key is temporary and can be cleaned when switching Streamlit pages.
    # Copy to a non-widget session key before navigating.
    st.session_state["radar_light_theme"] = bool(st.session_state["_radar_theme_toggle"])
    st.query_params["theme"] = "light" if st.session_state["radar_light_theme"] else "dark"


@st.cache_data(ttl=900, max_entries=2)
def _searchable_stocks(db_path, stamp):
    with sqlite3.connect(db_path) as conn:
        return conn.execute(
            """SELECT market,code,MAX(name) FROM daily
               WHERE date = (SELECT MAX(date) FROM daily)
                 AND market IN ('上市','上櫃')
               GROUP BY market,code ORDER BY code"""
        ).fetchall()


def show_top_nav(*, restore_db=True):
    """上方六個浮動分類與跨頁保留的黑／白模式。"""
    if restore_db:
        try:
            ensure_db()
        except (OSError, ValueError, sqlite3.DatabaseError) as exc:
            st.warning(f"完整歷史資料載入失敗，暫用舊版行情：{exc}")
    if "radar_light_theme" not in st.session_state:
        st.session_state["radar_light_theme"] = st.query_params.get("theme", "light") != "dark"
    elif st.query_params.get("theme") in ("light", "dark"):
        st.session_state["radar_light_theme"] = (st.query_params["theme"] == "light")
    # Restore widget state on every page, rather than relying on widget-key persistence.
    st.session_state["_radar_theme_toggle"] = bool(st.session_state["radar_light_theme"])
    st.markdown(_theme_css(bool(st.session_state["radar_light_theme"])), unsafe_allow_html=True)
    with st.container(key="radar_top_nav"):
        cols = st.columns([1, 1, 1.2, 1, 1, 1, 0.65, 1.0], gap="small", vertical_alignment="center")
        for col, (title, links) in zip(cols, MENUS):
            with col:
                with st.popover(title, use_container_width=True):
                    for label, path in links:
                        st.page_link(path, label=label, use_container_width=True)
        with cols[-2]:
            with st.popover("🔍 搜尋", use_container_width=True):
                db = Path(__file__).resolve().parent / "twstock.sqlite3"
                try:
                    if db.exists():
                        stocks = _searchable_stocks(str(db), db.stat().st_mtime_ns)
                    else:
                        stocks = []
                except sqlite3.Error:
                    stocks = []
                if stocks:
                    choices = {f"{m}:{c}": f"{c} {n}（{m}）" for m,c,n in stocks}
                    chosen = st.selectbox(
                        "搜尋代號／名稱", list(choices), index=None,
                        format_func=lambda k: choices[k],
                        placeholder="輸入代號或名稱", key="global_stock_search"
                    )
                    if st.button("查看個股圖表", disabled=not chosen, key="global_stock_open",
                                 use_container_width=True):
                        st.session_state["global_selected_stock"] = chosen
                        st.switch_page("pages/1_均線與法人籌碼.py")
                else:
                    st.caption("目前沒有可用的股票名單")
        with cols[-1]:
            st.toggle("☀️ 白底模式", key="_radar_theme_toggle",
                      on_change=_save_theme, help="關閉為黑底模式；切換後立即套用。")
