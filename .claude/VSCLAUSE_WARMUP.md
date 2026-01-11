# VSCLAUSE WARMUP INSTRUCTIONS

**File:** `.claude/VSCLAUSE_WARMUP.md`
**Copy this entire file into your new VSCode Claude chat**

---

## STEP 1: ORIENT YOURSELF

Run these commands to understand the project:

```bash
# Project root
cd "/Volumes/Satechi Hub/ZINC-FUSION-V15"

# See project structure
ls -la

# See frontend structure (where Inngest jobs live)
ls -la frontend/src/inngest/

# See existing docs
ls -la Docs/
```

---

## STEP 2: READ CRITICAL DOCS

Read these in order:

```bash
# 1. Your master reference (MUST READ FIRST)
cat Docs/RAW_SOURCE_SPECIALIST_MAPPING.md

# 2. See the Bronze v2.0 pattern (your template)
head -100 frontend/src/inngest/fred-daily.ts

# 3. See how jobs are exported
cat frontend/src/inngest/functions.ts

# 4. See how jobs are registered
cat frontend/src/app/api/inngest/route.ts
```

---

## STEP 3: CHECK DATABASE STATE

```bash
# See what raw tables exist
cd "/Volumes/Satechi Hub/ZINC-FUSION-V15"
npx tsx -e "
const { Pool } = require('pg');
require('dotenv').config();
const pool = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });
async function check() {
  const client = await pool.connect();
  const r = await client.query(\"SELECT table_name FROM information_schema.tables WHERE table_schema = 'raw' ORDER BY table_name\");
  console.log('=== RAW TABLES ===');
  r.rows.forEach(row => console.log(row.table_name));
  client.release();
  await pool.end();
}
check();
"
```

---

## STEP 4: CHECK ENV KEYS

```bash
# See what API keys are available locally
grep -E "API_KEY|TOKEN|SECRET" frontend/.env.local | grep -v "#"
```

---

## STEP 5: UNDERSTAND YOUR MISSION

You are **Track A: URL Load-ins & Inngest Jobs**

Your job:
1. Build Inngest jobs that pull from external APIs
2. Insert data into Bronze tables with proper `specialist_tags`
3. Follow the fred-daily.ts pattern exactly

**DO NOT TOUCH:**
- Schema definitions
- ops tables
- Anything Claude.ai (Track B) is working on

---

## STEP 6: START BUILDING

After warmup, start with:

```bash
# Create whitehouse.ts (highest priority)
# Template from fred-daily.ts
# Target: raw.legislation_whitehouse_1d (may need to create table)
# Tags: ["trump_effect"]
# URLs: 
#   - https://www.whitehouse.gov/briefing-room/statements-releases/feed/
#   - https://www.whitehouse.gov/presidential-actions/
```

---

## KEY RULES

1. **TARIFF ≠ TRUMP_EFFECT** - Different specialists, different data
2. All jobs use Bronze v2.0 pattern (ops logging, row_hash, specialist_tags)
3. All daily jobs: `cron: "0 11 * * 1-5"` (5AM CT)
4. Commit after each working job
5. Ask Kirk if stuck or need missing API keys

---

## YOUR CHECKLIST

- [ ] Ran orientation commands
- [ ] Read RAW_SOURCE_SPECIALIST_MAPPING.md
- [ ] Understand fred-daily.ts pattern
- [ ] Know which tables exist
- [ ] Know which API keys are available
- [ ] Ready to build whitehouse.ts

---

**When ready, say: "Warmup complete. Starting whitehouse.ts"**
