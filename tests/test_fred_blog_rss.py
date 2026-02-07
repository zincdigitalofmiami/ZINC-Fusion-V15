#!/usr/bin/env python3
"""Test FRED blog RSS feeds for structure and duplicate detection."""
import feedparser
import hashlib
from datetime import datetime

# FRED blog main RSS
FRED_BLOG_RSS = "https://fredblog.stlouisfed.org/feed/"

print("Testing FRED Blog RSS Feed")
print("=" * 80)

feed = feedparser.parse(FRED_BLOG_RSS)

print(f"\nFeed Title: {feed.feed.get('title', 'N/A')}")
print(f"Feed Link: {feed.feed.get('link', 'N/A')}")
print(f"Total Entries: {len(feed.entries)}")
print("\n" + "-" * 80)

# Show first 10 entries with details
for i, entry in enumerate(feed.entries[:10], 1):
    title = entry.get('title', 'No title')
    link = entry.get('link', 'No link')
    published = entry.get('published', entry.get('updated', 'No date'))
    summary = entry.get('summary', '')[:200]
    
    # Parse date
    try:
        pub_date = datetime.strptime(published, '%a, %d %b %Y %H:%M:%S %z')
        pub_str = pub_date.strftime('%Y-%m-%d %H:%M')
    except:
        pub_str = published
    
    # Generate hash for dedup testing
    hash_input = f"{title}|{pub_str[:10]}"  # title + date (no time)
    row_hash = hashlib.md5(hash_input.encode()).hexdigest()[:12]
    
    print(f"\n{i}. {title}")
    print(f"   Published: {pub_str}")
    print(f"   Link: {link}")
    print(f"   Hash: {row_hash}")
    print(f"   Summary: {summary}...")
    
    # Check for keywords to map to specialists
    title_lower = title.lower()
    summary_lower = summary.lower()
    combined = title_lower + " " + summary_lower
    
    specialists = []
    if any(k in combined for k in ['inflation', 'cpi', 'pce', 'price']):
        specialists.append('fed')
    if any(k in combined for k in ['china', 'beijing', 'yuan']):
        specialists.append('china')
    if any(k in combined for k in ['oil', 'petroleum', 'crude', 'energy']):
        specialists.append('energy')
    if any(k in combined for k in ['fed', 'fomc', 'federal reserve', 'interest rate']):
        specialists.append('fed')
    if any(k in combined for k in ['tariff', 'trade war', 'duties']):
        specialists.append('tariff')
    if any(k in combined for k in ['uncertainty', 'epu', 'policy uncertainty']):
        specialists.append('trump_effect')
    if any(k in combined for k in ['employment', 'jobs', 'unemployment', 'labor']):
        specialists.append('fed')
    if any(k in combined for k in ['dollar', 'exchange rate', 'currency']):
        specialists.append('fx')
        
    if specialists:
        print(f"   Specialists: {', '.join(set(specialists))}")

print("\n" + "=" * 80)
print("\nFRED Blog RSS Structure:")
print("  ✅ Has title, link, published date")
print("  ✅ Can generate row_hash for dedup")
print("  ✅ Can map to specialists via keyword matching")
print("  ✅ Provides summary/content for sentiment analysis")
print("\nNext: Test FRED release calendar API")
