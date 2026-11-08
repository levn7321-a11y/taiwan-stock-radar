# 台股 AI 突破雷達 V2.1 — 增量安裝

本壓縮檔**只新增檔案**，不覆蓋既有 `app.py`、`history.py`、`daily_update.py`、`storage.py`、`requirements.txt` 與 V2.0 排程。

## 新增檔案（請保留路徑）
- `pages/1_均線與法人籌碼.py`：Streamlit 新增頁面
- `ma_v21.py`：MA5、10、20、60、240 計算與訊號
- `institutional_v21.py`：上市、上櫃法人官方資料擷取
- `.github/workflows/institutional_v21.yml`：每日 18:10（台灣時間）排程、手動觸發
- `data/.gitkeep`：資料夾佔位；更新成功後產生 `data/institutional_daily.csv`

## 安裝
1. 在 GitHub `taiwan-stock-radar` 專案，使用 Add file → Upload files 上傳解壓縮後的檔案，**保留資料夾路徑**。
2. `Commit changes` 至 `main`。
3. 在 GitHub Actions 找 `Institutional daily V2.1` → `Run workflow` → `main` → 執行。
4. 執行成功後確認專案 `data/institutional_daily.csv` 已新增，並重新開啟 Streamlit；左側選單應出現「均線與法人籌碼」。
5. 均線頁先透過 CSV 上傳歷史行情（至少 `date,market,code,name,close`）。**目前尚未自動連接 V2.0 的 SQLite 資料庫**，因尚未取得其 schema。

## 注意
- 官方法人資料可能有休市日、延後發布、格式改版或 API 暫時不可用；執行失敗請看 Actions logs。
- 上櫃 API 欄位若改版，程式會報錯而不產生猜測數字。
- 股數轉張數採 `/1000`；排行以買賣超張數排序。
- 只保留四位數股票代碼作為一般股票初步篩選，無法完全排除全部非普通股證券。
- 不保證第一次就能取得上櫃資料：需以實際 Actions logs 驗證官方回應。
- V2.1 是規則型分析，不是機器學習預測模型。
