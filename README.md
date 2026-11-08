# 台股 AI 突破雷達 V2 — 獨立網站部署版

本專案是 **日線規則選股工具**，不是已訓練的 AI 股價預測模型；新聞、法人及主力尚未串接。分數不是勝率，也不代表買賣建議。

## 立即部署成獨立網站（Streamlit Community Cloud）

1. 在 GitHub 建立一個新的 repository，將本資料夾**所有內容（包含 `.github/workflows/daily.yml`）**上傳到 repository 根目錄。
2. 到 https://share.streamlit.io/ ，以 GitHub 登入，選 **Create app → Deploy a public app from GitHub**。
3. 選 repository、branch `main`、入口檔 `app.py`，按 **Deploy**。部署完成後會取得可分享的網站網址。
4. 到 GitHub repository 的 **Actions → Taiwan stock daily refresh → Run workflow**，在 `backfill_days` 填 `120`，啟動第一次歷史回補。**首次請在 GitHub Actions 做回補**，避免在 Streamlit Cloud 網頁內回補後因容器重啟而遺失。
5. 回補完成後，Actions 將資料庫 `twstock.sqlite3` 提交到 repository。等 Streamlit Cloud 同步部署後，網頁即會讀取歷史資料並顯示排行。
6. 此後 GitHub Actions 會在**台灣時間週一至週五 17:30**（UTC 09:30）嘗試更新。遇台股休市會保留最後交易日資料；請以網站「最新資料日期」核對是否更新。

> GitHub Actions 排程並非保證準時，可能延遲或漏執行；請在 Actions 檢查是否成功。公開 repository 的資料庫及程式會公開，請勿存入帳密、個人交易紀錄或任何秘密。Streamlit Cloud 免費方案、GitHub Actions 配額與使用條款可能調整。官方站點可能拒絕雲端 IP 或變更欄位，無法保證回補成功。若雲端抓取失敗，請本機執行回補後再提交資料庫。

## 本機測試（Windows / macOS / Linux）

```bash
python -m pip install -r requirements.txt
python daily_update.py --backfill-days 120
python -m streamlit run app.py
```

`python daily_update.py` 僅抓最新收盤快照。`python -m unittest discover -s tests` 可跑解析器單元測試。歷史回補預設每日每市場一個請求，兩市場 120 天約 170 個 HTTP 請求，含 0.5 秒節流，可能需數分鐘。若出現錯誤，會列出失敗日期，不會假造數據；重跑會以日期＋市場＋代號去重覆蓋。

## 技術架構

- Streamlit：網站前端、選股表、下載 CSV
- SQLite：日線行情，GitHub Actions 每次更新後提交到 repo，供雲端重新部署讀取
- TWSE：`MI_INDEX` 指定日期上市全市場 OHLCV
- TPEx：`afterTrading/dailyQuotes` 指定日期上櫃全市場 OHLCV
- 最新快照：TWSE OpenAPI `STOCK_DAY_ALL`、TPEx OpenAPI `tpex_mainboard_daily_close_quotes`

## 選股規則

- 至少 61 個交易日的個股行情；比較今日收盤是否突破前 20 / 60 日最高價
- 量比＝當日成交股數 / 前 20 日平均成交股數
- 20、60 日均線、收盤位置、單日漲幅、成交金額與過熱警示
- 預設成交金額至少 3,000 萬元，量比 1.8 倍
- 排行榜僅顯示最新資料日期的個股，避免混入停牌或過期訊號

## 已知限制及下一階段

- **官方歷史端點格式可能調整，尚未在本環境成功做完整外網端到端測試**；如欄位不符會顯示錯誤，需依官方回應修正解析器。
- 未還原除權息、減資、股票分割；公司行動可能造成假突破，正式交易前須處理。
- 4 位數股票代號篩選仍可能包含 ETF 等非普通股；需新增官方證券基本資料白名單。
- 排程後可能有資料缺口；建議每週另行補抓近 7 日或加入缺漏檢查。
- 未加入新聞、外資、主力分點、歷史績效回測、交易成本及停損模型。
- 共享網站請勿依賴側欄手動更新作為永久資料寫入；容器重啟可能還原，正式更新應走 GitHub Actions。
