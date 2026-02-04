# ProFarmer Exhaustive Scraping - In Progress

## Status: Running Exhaustively Through All Sitemaps

**Started**: January 31, 2026  
**Scraper**: `scripts/scrape_profarmer_EXHAUSTIVE.js`  
**Process**: Running in background (PID logged to `/tmp/profarmer_exhaustive.log`)

### Strategy

Scraping **ALL** available monthly sitemaps from ProFarmer:
- **2016-11** through **2026-01** (111 months total)
- Each sitemap contains all news articles published that month
- Extracting complete metadata for each article

### Current Progress

- **Articles scraped**: 1,195+ (and counting)
- **Target**: Exhaust all available content
- **Monitor**: `tail -f /tmp/profarmer_exhaustive.log`

### Sitemaps Coverage

ProFarmer has sitemaps for these periods:
```
2016-11, 2017-05, 2017-08, 2017-09, 2017-10, 2017-11, 2017-12
2018-01, 2018-02, 2018-03, 2018-08, 2018-10, 2018-11
2019-03, 2019-04, 2019-05, 2019-06, 2019-07, 2019-08, 2019-09, 2019-10, 2019-11, 2019-12
2020-01 through 2020-12
2021-01 through 2021-12
2022-01 through 2022-12
2023-01 through 2023-12
2024-01 through 2024-12
2025-01 through 2025-12
2026-01
```

**Note**: Some early sitemaps (2016-2020) appear to have 0 news URLs, meaning ProFarmer's public archive may only go back to 2021.

### Metadata Being Extracted

For each article:
- ✅ event_date (publication date)
- ✅ headline (title)
- ✅ content (full text)
- ✅ summary (from meta description)
- ✅ subject (section/category)
- ✅ tags (article tags)
- ✅ topics (combined categories + tags)
- ✅ keywords (meta keywords)
- ✅ categories (from breadcrumbs)
- ✅ specialist_tags (auto-assigned)
- ✅ author (if available)
- ✅ url (unique identifier)
- ✅ raw_payload (full JSON with all metadata)

### Cleanup Completed While Running

✅ Removed `sentiment_score` from:
- `alt.news_1d` (only 1/1301 rows used it)
- `alt.econ_news` (0 rows used it)
- `econ.news_event` (0 rows used it)

✅ Kept `sentiment_score` in:
- `features.news_sentiment_1d` (that's its purpose)

✅ Kept `ingestion_batch_id` in tables that use it:
- `alt.legislation_1d` (100% usage)
- `econ.news_event` (100% usage)
- `supply.lcfs_1d` (100% usage)
- `alt.news_1d` (91% usage)

### Let It Run

The scraper will continue until it has processed ALL 111 monthly sitemaps and attempted to scrape every article URL found. This ensures we have the most complete ProFarmer archive possible.

**Monitor command**: `tail -f /tmp/profarmer_exhaustive.log`

---

**Current Status**: ✅ Running - will exhaust all sitemaps automatically
