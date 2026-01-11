# VSCLAUSE STARTUP PROMPT

Copy this entire block into VSCode Claude:

---

## YOUR MISSION

You are VSClaude, working on **Track A: URL Load-ins & Inngest Jobs** for ZINC-FUSION-V15.

Your job: Build Inngest jobs to pull data from external APIs into Bronze tables.

**DO NOT TOUCH:**
- Raw schema definitions
- Bronze contract/ops tables
- Anything in Track B (Claude.ai is handling that)

---

## FIRST STEP

Read the master document:
```
/Volumes/Satechi Hub/ZINC-FUSION-V15/Docs/RAW_SOURCE_SPECIALIST_MAPPING.md
```

This contains:
- ⚠️ TARIFF vs TRUMP_EFFECT separation rules (CRITICAL)
- 🔑 API keys available
- 📋 Bronze v2.0 job template
- 📁 File locations
- URLs for each job to build
- Specialist tag assignments

---

## JOBS TO BUILD (Priority Order)

### LEGISLATION (6 jobs) - CRITICAL for trump_effect/tariff
1. `whitehouse.ts` → WhiteHouse.gov RSS + scrape
2. `federal-register.ts` → Federal Register API
3. `ustr.ts` → USTR scrape
4. `epa.ts` → EPA RSS + RIN scrape
5. `congress.ts` → Congress API (KEY NEEDED)
6. `ice.ts` → ICE/DHS RSS

### ENERGY (2 jobs)
7. `eia-inventories.ts` → EIA API (KEY NEEDED)
8. `eia-production.ts` → EIA API (KEY NEEDED)

### AGRICULTURE (2 jobs)
9. `nopa.ts` → NOPA PDF scrape
10. `conab.ts` → CONAB scrape

### TRADE (3 jobs)
11. `gacc.ts` → China customs (complex)
12. `mpob.ts` → Malaysia palm (scrape)
13. `usitc.ts` → USITC trade data

### SENTIMENT (2 jobs)
14. `social.ts` → ScrapeCreators API ✅ KEY AVAILABLE
15. `polymarket.ts` → Polymarket API (replace crowd-beliefs.ts)

---

## BRONZE PATTERN REFERENCE

Use `frontend/src/inngest/fred-daily.ts` as your template.

Key requirements:
1. Log to `ops.ingest_run` at start
2. Compute `row_hash` for idempotency
3. Assign `specialist_tags[]` per mapping doc
4. Update `ops.ingest_run` on completion
5. Cron: `0 11 * * 1-5` (5AM CT Mon-Fri)

---

## AFTER CREATING EACH JOB

1. Add export to `frontend/src/inngest/functions.ts`
2. Add to array in `frontend/src/app/api/inngest/route.ts`
3. Commit and push:
```bash
cd "/Volumes/Satechi Hub/ZINC-FUSION-V15/frontend"
git add src/inngest/NEW_JOB.ts src/inngest/functions.ts src/app/api/inngest/route.ts
git commit -m "feat: add NEW_JOB Bronze ingestion"
git push
```

---

## KEY RULES

1. **TARIFF ≠ TRUMP_EFFECT** - Read the separation rules!
2. Every job uses Bronze v2.0 pattern
3. All daily jobs run at 5AM CT (11 UTC)
4. Ask Kirk if you need API keys that aren't available
5. Test locally before committing if possible

---

## START HERE

Begin with `whitehouse.ts` - it's the highest priority for trump_effect specialist data.

Read the mapping doc first, then build.
