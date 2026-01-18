#!/usr/bin/env python3
"""Test if Barchart search supports date filtering."""
from playwright.sync_api import sync_playwright
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
COOKIES_PATH = PROJECT_ROOT / ".barchart_cookies.json"

# Test different URL patterns
test_urls = [
    "https://www.barchart.com/news/search/any/soybean+oil",
    "https://www.barchart.com/news/search/any/soybean+oil?date_from=2024-01-01",
    "https://www.barchart.com/news/search/any/soybean+oil?dateFrom=2024-01-01",
    "https://www.barchart.com/news/search/any/soybean+oil?startDate=2024-01-01",
    "https://www.barchart.com/news/search/any/soybean+oil?from=2024-01-01",
]

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context()
    
    # Load cookies
    if COOKIES_PATH.exists():
        with open(COOKIES_PATH) as f:
            cookies = json.load(f)
        context.add_cookies(cookies)
        print(f"Loaded {len(cookies)} cookies")
    
    page = context.new_page()
    
    for url in test_urls:
        print(f"\nTesting: {url}")
        page.goto(url, timeout=30000)
        page.wait_for_load_state("networkidle", timeout=10000)
        
        # Check URL after redirect
        print(f"  Final URL: {page.url}")
        
        # Extract first article date
        feed_element = page.query_selector("[data-feed-items]")
        if feed_element:
            feed_json = feed_element.get_attribute("data-feed-items")
            if feed_json:
                items = json.loads(feed_json)
                if items:
                    print(f"  First article: {items[0].get('title', '')[:60]}")
                    print(f"  Published: {items[0].get('published', '')}")
        
        input("Press Enter to continue...")
    
    browser.close()
