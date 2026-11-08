
name: V2.6.5 法人資料缺口修復

on:
  workflow_dispatch:
    inputs:
      apply:
        description: "是否正式補抓並寫入資料庫"
        required: true
        type: boolean
        default: false

permissions:
  contents: write

concurrency:
  group: twstock-database-update
  cancel-in-progress: false

jobs:
  repair:
    runs-on: ubuntu-latest

    steps:
      - name: 下載專案
        uses: actions/checkout@v4

      - name: 設定 Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: 安裝套件
        run: pip install requests

      - name: 檢查法人缺口
        run: python repair_v265.py --days 45 --limit 8

      - name: 正式修復法人資料
        if: ${{ inputs.apply == true }}
        run: python repair_v265.py --days 45 --limit 8 --apply

      - name: 儲存資料庫
        if: ${{ inputs.apply == true }}
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add twstock.sqlite3
          if ! git diff --cached --quiet; then
            git commit -m "V2.6.5 repair missing institutional data"
            git pull --rebase origin main
            git push origin HEAD:main
          else
            echo "資料庫沒有變更"
          fi
