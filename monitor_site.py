"""A 網站的真實瀏覽器監控：HTTP + Streamlit health + 畫面內容。

單純檢查 HTTP 200 會漏掉 Streamlit 客戶端「Oh no. Error running app」。
這個腳本用 Chromium 真正載入首頁，並等待台股頁面標題或錯誤文字。
"""
import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import requests
from playwright.sync_api import sync_playwright


def check_once(url, screenshot_path, timeout_ms=90000):
    started = time.monotonic()
    response = requests.get(url, timeout=25, headers={"User-Agent": "TaiwanStockRadar-UptimeMonitor/1.0"})
    response.raise_for_status()
    health = url.rstrip("/") + "/_stcore/health"
    # Streamlit Cloud may route /_stcore/health to the SPA HTML shell.
    # Treat its content as advisory, not a fatal error: only the real browser
    # rendering below can establish whether users see the app or an Oh no screen.
    try:
        resp = requests.get(health, timeout=15)
        if resp.status_code == 200 and resp.text.strip().lower() == "ok":
            print("HEALTH_ENDPOINT_OK", flush=True)
        else:
            print(f"HEALTH_ENDPOINT_INCONCLUSIVE status={resp.status_code}; checking rendered UI", flush=True)
    except requests.RequestException as exc:
        print(f"HEALTH_ENDPOINT_UNAVAILABLE: {type(exc).__name__}; checking rendered UI", flush=True)

    # Streamlit can return HTTP 200 even when the app displays its fatal error UI.
    with sync_playwright() as browser_tools:
        browser = browser_tools.chromium.launch(headless=True)
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            page.wait_for_function(
                """() => {
                    const text = document.body?.innerText || '';
                    return text.includes('台股 AI 突破雷達')
                        || text.includes('Error running app')
                        || text.includes('Oh no.');
                }""",
                timeout=timeout_ms,
            )
            text = page.locator("body").inner_text(timeout=15000)
            if "Oh no." in text or "Error running app" in text:
                raise RuntimeError("Browser displays fatal Streamlit 'Oh no' error")
            if "台股 AI 突破雷達" not in text:
                raise RuntimeError("Homepage heading did not render")
            return round(time.monotonic()-started, 2)
        except Exception:
            try:
                page.screenshot(path=str(screenshot_path), full_page=True, timeout=15000)
            except Exception:
                pass
            raise
        finally:
            browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://taiwan-stock-radar-7321.streamlit.app/")
    parser.add_argument("--output", default="site-monitor-result.json")
    parser.add_argument("--screenshot", default="site-monitor-failure.png")
    parser.add_argument("--attempts", type=int, default=2)
    args = parser.parse_args()
    errors = []
    success = False
    latency = None
    for attempt in range(1, max(1, args.attempts)+1):
        try:
            latency = check_once(args.url, Path(args.screenshot))
            success = True
            break
        except Exception as exc:
            errors.append(f"attempt {attempt}: {type(exc).__name__}: {exc}")
            if attempt < args.attempts:
                time.sleep(15)
    data = {
        "checked_at_taipei": datetime.now(ZoneInfo("Asia/Taipei")).isoformat(timespec="seconds"),
        "url": args.url, "status": "healthy" if success else "unhealthy",
        "attempts": len(errors)+int(success), "load_seconds": latency,
        "errors": errors,
    }
    Path(args.output).write_text(json.dumps(data, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
