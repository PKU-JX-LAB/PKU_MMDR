"""Headless Chrome screenshot for local HTML chart files (optional: selenium)."""

from __future__ import annotations

import os
import time
from pathlib import Path


def render_page(folder_path: str, page_file_name: str, screenshot_folder: str):
    """
    Load file:// HTML in headless Chrome and save a full-page PNG.

    Returns:
        (screenshot_path | None, console_message, width_px, height_px)
    """
    html_path = os.path.abspath(os.path.join(folder_path, page_file_name))
    if not os.path.isfile(html_path):
        return None, f"Missing HTML: {html_path}", 0, 0

    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
    except ImportError:
        return None, "selenium not installed; pip install selenium", 0, 0

    file_url = Path(html_path).as_uri()
    base_name = os.path.splitext(page_file_name)[0]
    out_path = os.path.join(screenshot_folder, f"{base_name}_screenshot.png")

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=1920,2000")
    options.add_argument("--hide-scrollbars")

    driver = None
    try:
        driver = webdriver.Chrome(options=options)
        driver.get(file_url)
        time.sleep(0.8)
        width = driver.execute_script(
            "return Math.max(document.body.scrollWidth, document.documentElement.scrollWidth)"
        )
        height = driver.execute_script(
            "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
        )
        if width and height:
            driver.set_window_size(int(width) + 40, int(height) + 40)
            time.sleep(0.3)
        driver.save_screenshot(out_path)
        if not os.path.isfile(out_path):
            return None, "screenshot file was not written", 0, 0
        w = driver.execute_script("return window.innerWidth") or 0
        h = driver.execute_script("return window.innerHeight") or 0
        return out_path, "", int(w), int(h)
    except Exception as exc:
        return None, str(exc), 0, 0
    finally:
        if driver is not None:
            driver.quit()
