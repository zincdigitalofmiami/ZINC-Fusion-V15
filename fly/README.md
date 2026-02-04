# Fly.io Databento Live Connector
Forward fill policy: [Docs/FORWARD_FILL_POLICY.md](Docs/FORWARD_FILL_POLICY.md)


Real-time ZL intraday data for dashboard charts.

## Setup (One-Time)

### 1. Install Fly CLI

```bash
# macOS
brew install flyctl

# Or via curl
curl -L https://fly.io/install.sh | sh
```

### 2. Create Fly.io Account & Login

```bash
fly auth signup
# or if you have an account:
fly auth login
```

### 3. Deploy from the fly/ directory

```bash
cd fly

# Create the app (first time only)
fly launch --name zinc-databento-live --region ord --no-deploy

# Set secrets (get these from your .env file)
fly secrets set DATABENTO_API_KEY="your_key_here"
fly secrets set DATABASE_URL="your_postgres_url_here"
fly secrets set INNGEST_EVENT_KEY="your_inngest_key_here"

# Deploy
fly deploy
```

### 4. Verify it's running

```bash
fly status
fly logs
```

## Management

```bash
# View logs
fly logs -a zinc-databento-live

# Restart
fly apps restart zinc-databento-live

# Stop (pause billing)
fly scale count 0 -a zinc-databento-live

# Resume
fly scale count 1 -a zinc-databento-live

# Destroy (delete everything)
fly apps destroy zinc-databento-live
```

## Cost

- **Free tier**: 3 shared-cpu-1x VMs with 256MB RAM
- **This app uses**: 1 VM
- **Expected cost**: $0/month (within free tier)

## What it does

1. Connects to Databento Live TCP feed for ZL.n.0
2. Aggregates 1-minute bars into 15m, 1h, 1d bars
3. Sends events to Inngest → writes to analytics tables
4. Runs in 6-hour cycles, auto-restarts on completion/failure
5. On restart, replays last 30 minutes to catch any gaps

## Data Flow

```
Databento Live (TCP)
       ↓
  ingest_databento_live_zl.py (Fly.io)
       ↓
  Inngest Events (zl.bar.15m, zl.bar.1h, zl.bar.1d)
       ↓
  Vercel Functions (zl-live.ts handlers)
       ↓
  PostgreSQL (analytics.zl_price_*)
       ↓
  Dashboard Charts (real-time!)
```
