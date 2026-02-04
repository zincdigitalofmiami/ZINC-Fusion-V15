# GPT Codex Setup Guide: ZINC-FUSION-V15

Welcome to the ZINC-FUSION-V15 project. This guide will walk you through getting set up with Vercel, Prisma, and the repo from scratch.

---

## Prerequisites (Install These First)

### 1. Node.js 22.x (Required)

```bash
# Using nvm (recommended)
nvm install 22
nvm use 22

# Or using Homebrew (macOS)
brew install node@22
```

Verify: `node --version` should show `v22.x.x`

### 2. npm 10.x (Comes with Node 22)

Verify: `npm --version` should show `10.x.x`

### 3. Python 3.11+ with venv

```bash
# macOS
brew install python@3.11

# Create virtual environment (from repo root)
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 4. Vercel CLI

```bash
npm install -g vercel
```

Verify: `vercel --version`

### 5. Prisma CLI (Installed locally, but good to know)

```bash
# From repo root (already in package.json)
npm install
npx prisma --version
```

---

## CLIs You'll Use

| CLI | Install Command | Purpose |
|-----|-----------------|---------|
| `vercel` | `npm i -g vercel` | Deploy frontend, manage env vars |
| `prisma` | `npm i prisma` (local) | Schema management, migrations |
| `gh` | `brew install gh` | GitHub CLI for PRs, issues |
| `node` | See above | Run JS/TS scripts |
| `python` | See above | ML pipelines, training |

---

## Repository Structure

```
ZINC-FUSION-V15/
├── frontend/           # Next.js 16 dashboard (Vercel deployment)
│   ├── src/
│   │   ├── app/        # App router pages
│   │   ├── components/ # React components
│   │   ├── lib/        # Utilities (db.ts = pg Pool)
│   │   └── inngest/    # Background jobs
│   └── package.json    # Node 22.x, npm 10.x
├── prisma/
│   └── schema.prisma   # Database schema (source of truth)
├── src/fusion/         # Python ML code
├── scripts/            # Utility scripts
├── .env                # Environment variables (DO NOT COMMIT)
└── package.json        # Root package (Prisma deps)
```

---

## Step-by-Step Setup

### Step 1: Clone the Repository

```bash
git clone <repo-url> ZINC-FUSION-V15
cd ZINC-FUSION-V15
```

### Step 2: Install Root Dependencies (Prisma)

```bash
# From repo root
npm install
```

This installs:
- `prisma` (schema management)
- `@prisma/client` (generated client)
- `@prisma/adapter-pg` (PostgreSQL adapter)

### Step 3: Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### Step 4: Set Up Environment Variables

Create a `.env` file in the repo root:

```bash
# Required
DATABASE_URL="postgresql://user:password@host:port/database?sslmode=require"

# Optional (for specific features)
FRED_API_KEY="your-fred-api-key"
DATABENTO_API_KEY="your-databento-key"
ANTHROPIC_API_KEY="your-anthropic-key"
```

**CRITICAL:** Never commit `.env` to git. It's in `.gitignore`.

For the frontend, create `frontend/.env.local`:

```bash
DATABASE_URL="postgresql://user:password@host:port/database?sslmode=require"
```

### Step 5: Verify Prisma Connection

```bash
# Generate Prisma client
npx prisma generate

# Test connection (opens Prisma Studio)
npx prisma studio
```

If Prisma Studio opens and shows tables, you're connected.

### Step 6: Log In to Vercel

```bash
vercel login
```

This opens a browser for authentication.

### Step 7: Link to Vercel Project

```bash
cd frontend
vercel link
```

Follow the prompts to link to the existing project or create a new one.

### Step 8: Pull Environment Variables from Vercel

```bash
vercel env pull .env.local
```

This syncs Vercel's environment variables to your local `.env.local`.

### Step 9: Run Frontend Locally

```bash
cd frontend
npm run dev
```

Open http://localhost:3000 to see the dashboard.

### Step 10: Set Up Python Environment

```bash
# From repo root
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Verify:
```bash
.venv/bin/python -c "import fusion; print('OK')"
```

---

## Key Commands Reference

### Prisma Commands

```bash
# Generate client after schema changes
npx prisma generate

# Create a migration (schema changes)
npx prisma migrate dev --name describe_your_change

# Apply migrations to production
npx prisma migrate deploy

# Open database GUI
npx prisma studio

# Pull existing schema from database
npx prisma db pull

# Push schema without migration (dev only)
npx prisma db push
```

### Vercel Commands

```bash
# Deploy to preview
vercel

# Deploy to production
vercel --prod

# List deployments
vercel ls

# Check logs
vercel logs <deployment-url>

# Pull env vars
vercel env pull

# Add env var
vercel env add VARIABLE_NAME
```

### Frontend Commands

```bash
cd frontend

# Development server
npm run dev

# Production build
npm run build

# Lint code
npm run lint

# Run tests
npm test
```

### Python Commands

```bash
# Always use .venv
source .venv/bin/activate

# Run tests
.venv/bin/pytest -q

# Run API server
.venv/bin/python -m uvicorn fusion.api.server:app --host 0.0.0.0 --port 8000

# Run specific training
.venv/bin/python -m fusion.core_training.run_pipeline --horizons 5
```

---

## Database Architecture (Important!)

**Prisma manages schema only. Runtime queries use raw SQL.**

| Layer | Tool | File |
|-------|------|------|
| Schema | Prisma | `prisma/schema.prisma` |
| TypeScript queries | pg Pool | `frontend/src/lib/db.ts` |
| Python queries | psycopg2 | `src/fusion/db/connection.py` |

**DO NOT** try to use PrismaClient for runtime queries. This is intentional architecture.

**Schema Layout (Multi-Schema):**
- `mkt.*` - Market data (futures, options)
- `econ.*` - Economic indicators
- `training.*` - ML training tables
- `forecasts.*` - Model outputs
- `analytics.*` - Dashboard views

---

## Common Gotchas

### 1. Wrong Node Version
```bash
# Check version
node --version  # Must be 22.x

# Fix with nvm
nvm use 22
```

### 2. Prisma Client Not Generated
```bash
npx prisma generate
```

### 3. Database Connection Refused
- Check `DATABASE_URL` in `.env`
- Ensure SSL mode is correct (`?sslmode=require`)
- Check if IP is whitelisted in Prisma/Neon dashboard

### 4. Python Import Errors
```bash
# Always activate venv first
source .venv/bin/activate

# Or use explicit path
.venv/bin/python your_script.py
```

### 5. Vercel Build Fails
```bash
# Check build locally first
cd frontend && npm run build
```

---

## Files You Should Read

1. **`AGENTS.md`** - Primary operating rules and architecture
2. **`CLAUDE.md`** - Additional context and constraints
3. **`prisma/schema.prisma`** - Database schema (source of truth)
4. **`frontend/src/lib/db.ts`** - How TypeScript queries the database
5. **`src/fusion/db/connection.py`** - How Python queries the database

---

## Quick Verification Checklist

- [ ] `node --version` shows 22.x
- [ ] `npm --version` shows 10.x
- [ ] `vercel --version` works
- [ ] `npx prisma --version` works
- [ ] `.env` has `DATABASE_URL` set
- [ ] `npx prisma studio` opens and shows tables
- [ ] `cd frontend && npm run dev` starts without errors
- [ ] `.venv/bin/python -c "import fusion"` works

---

## Getting Help

- Check `AGENTS.md` for architectural decisions
- Check `Docs/` folder for specific topics
- Never invent schemas/tables - verify they exist first
- When in doubt, read the code before modifying

Welcome aboard! 🚀
