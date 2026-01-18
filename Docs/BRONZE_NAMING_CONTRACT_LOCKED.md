# BRONZE NAMING CONTRACT — LOCKED (v2026-01-11)

**Status:** LOCKED  
**Date:** January 11, 2026  
**Authority:** Kirk (Architect)

> NOTE (2026-01-17): Schema v2 deprecates raw/bronze usage. This contract is legacy.

---

## 0) Scope

Applies to every table in `raw.*` (Bronze). Purpose is PIT correctness, revision tracking, reproducible training, and audit-grade provenance.

---

## 1) Table Naming Grammar

### 1.1 Canonical Format

```
raw.<provider>_<dataset>_<cadence>
```

Where:
- `<provider>` = authoritative origin (not transport layer)
  - Examples: `fred`, `cftc`, `usda`, `epa`, `eia`, `noaa`, `yahoo`, `ice`, `dhs`, `cbp`
- `<dataset>` = stable noun phrase describing what the table is (not how it's used)
  - Examples: `observations`, `cot`, `cits`, `wasde`, `export_sales`, `rin_prices`, `equity`, `articles`
- `<cadence>` = one of the allowed suffixes (below)

### 1.2 Allowed Cadence Suffixes (LOCKED)

| Suffix | Meaning | Use Case |
|--------|---------|----------|
| `_1h` | Hourly | Sub-daily bars or hourly observations |
| `_1d` | Daily | Daily time series |
| `_1w` | Weekly | Weekly releases |
| `_1m` | Monthly | Monthly releases |
| `_event` | Event-time | Irregular publication (press releases, notices, trades, announcements) |
| `_static` | Reference data | Metadata, lookup tables, dimension data |

**Explicitly disallowed:** `_1y`, `_daily`, `_weekly`, `_archive`, `_hist`, `_bronze`, `_silver`, etc.

### 1.3 Decision Rule: Cadence Selection (Deterministic)

```
Is it reference/dimension/lookup and not time-updating as a "series"?
  └─ YES → _static

Does it arrive as discrete releases, notices, actions, stories, filings, or "things that happen"?
  └─ YES → _event

Else if it is time-indexed at a fixed interval:
  └─ Choose one of _1h/_1d/_1w/_1m
```

**Annual releases** (e.g., "yearly NASS tables") are treated as publication events in Bronze unless the system formally supports `_1y`. Therefore: `_event`.

---

## 2) Prohibited Naming Patterns (Hard Fails)

### 2.1 No Missing Cadence Suffix

❌ BAD:
- `raw.fred_series_metadata`
- `raw.news_articles_archive`

✅ GOOD:
- `raw.fred_series_static`
- `raw.news_articles_event`

### 2.2 No Semantic Pollution in Names

Disallow adding:
- **Storage intent:** `archive`, `backup`, `old`, `tmp`
- **Processing stage:** `bronze`, `silver`, `gold`
- **Operational routing:** `core`, `specialist`, `training`

Those belong in columns (`specialist_tags`, provenance, etc.) and schemas (`raw/ops/metadata/...`), not table names.

---

## 3) Canonical Resolutions for Current Violations

| Current Name | Action | New Name | Rationale |
|--------------|--------|----------|-----------|
| `raw.usda_nass_1y` | RENAME | `raw.usda_nass_event` | Annual publications are event releases |
| `raw.fred_series_metadata` | RENAME | `raw.fred_series_static` | Reference/dimension data |
| `raw.news_articles_archive` | RENAME or DELETE | `raw.news_articles_event` | News is event-time (or DELETE if quarantine) |
| `raw.cftc_cits_1w` | KEEP | `raw.cftc_cits_1w` | Valid name, distinct from COT |
| `raw.whitehouse_actions_event` | KEEP | `raw.whitehouse_actions_event` | Valid name (empty, being rebuilt) |

---

## 4) Cross-Table Identity and Keys

### 4.1 Entity Key Conventions

Use consistent entity identifiers:
- `series_id` (FRED)
- `symbol` (futures/options)
- `report_date` or `release_id` where applicable
- `article_id` / `url_hash` for news

### 4.2 No Uniqueness on (entity_key, event_date)

This is contract-critical for revisions/PIT:
- ✅ Index allowed
- ❌ Unique constraint forbidden

---

## 5) Operational Implication

Suffix drives:
- PIT join strategy (`event_date` + `knowledge_time`)
- Expected release lag checks
- Validator expectations (e.g., `_static` tables may allow null `event_date` only if explicitly exempted)
- Automated routing/tagging rules and aggregation pipelines

**Naming is executable metadata, not cosmetics.**

---

## 6) Minimal Glossary

| Suffix | Semantics |
|--------|-----------|
| `_static` | Reference/dimension table; updates allowed but not modeled as time series |
| `_event` | Event-time row semantics; irregular arrival; revisions via `revision_no` + `knowledge_time` |
| `_1d/_1w/_1m/_1h` | Fixed cadence time series |

---

*LOCKED — Kirk Authority*
