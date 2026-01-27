#!/usr/bin/env python3
"""Debug script to inspect Barchart news page structure."""

raise SystemExit(
    "Barchart debug tooling is disabled in production. Existing data is retained."
)

from playwright.sync_api import sync_playwright
import json
from pathlib import Path

COOKIES_PATH = Path(".barchart_cookies.json")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()

    # Load cookies
    with open(COOKIES_PATH, "r") as f:
        cookies = json.load(f)
    context.add_cookies(cookies)

    page = context.new_page()
    page.goto("https://www.barchart.com/news/search/any/china")

    import time

    time.sleep(5)  # Wait for JS to load

    print("Page title:", page.title())
    print("URL:", page.url)

    # Try various selectors
    selectors = [
        "article",
        ".bc-news-item",
        "tr",
        ".news-item",
        "table tbody tr",
        "[data-ng-repeat]",
        ".bc-datatable tbody tr",
        ".bc-table-scrollable-inner tbody tr",
        "div[class*='news']",
        "a[href*='/news/']",
    ]

    for sel in selectors:
        elements = page.query_selector_all(sel)
        print(f"Selector '{sel}': {len(elements)} elements")

    # Save HTML for analysis
    with open("/tmp/barchart_debug.html", "w") as f:
        f.write(page.content())
    print("\nSaved HTML to /tmp/barchart_debug.html")

    # Find all links containing /news/
    news_links = page.query_selector_all("a[href*='/news/']")
    print(f"\nFound {len(news_links)} news links")
    for link in news_links[:10]:
        href = link.get_attribute("href")
        text = link.inner_text()[:50]
        print(f"  {text}: {href}")

    input("\nPress Enter to close browser...")
    browser.close()
