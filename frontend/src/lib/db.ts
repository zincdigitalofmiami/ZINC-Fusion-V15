/**
 * Database client for Prisma Postgres
 * Queries institutional schema tables (mkt.*, econ.*, features.*, etc.) at runtime
 *
 * Pool tuning rationale (serverless on Vercel → Prisma Postgres):
 *   max=2        — each Lambda gets at most 2 connections; prevents pool saturation
 *                  when many functions cold-start simultaneously (62 Inngest jobs × 4
 *                  was 248 potential connections vs. a 50-connection server limit).
 *   connect 10s  — Prisma Postgres proxy can be slow under load; 5s caused false
 *                  timeouts during Inngest cron bursts.  10s × 3 retries = 31.5s
 *                  worst-case, safely under Vercel's 60s function timeout.
 *   idle 5s      — release connections quickly so other Lambda instances can use them.
 *   retry 3×     — exponential backoff on connect() handles transient proxy hiccups.
 */
import { Pool } from 'pg'
import type { PoolClient } from 'pg'

/* ------------------------------------------------------------------ */
/*  Pool configuration                                                 */
/* ------------------------------------------------------------------ */

type GlobalDbPool = {
  __zincDbPool?: Pool
}

const globalDb = globalThis as unknown as GlobalDbPool

const LOCAL_DB_HOSTS = new Set([
  'localhost',
  '127.0.0.1',
  '::1',
  '0.0.0.0',
  'host.docker.internal',
])

type PgSslOption = false | { rejectUnauthorized: false }

function resolveConnectionString(): string | undefined {
  const raw =
    process.env.DATABASE_URL ??
    process.env.POSTGRES_URL ??
    process.env.DIRECT_DATABASE_URL
  if (!raw) return undefined
  const trimmed = raw.trim()
  return trimmed.length > 0 ? trimmed : undefined
}

function parseConnectionString(
  connectionString: string
): URL | undefined {
  try {
    return new URL(connectionString)
  } catch {
    return undefined
  }
}

function shouldDisableSsl(
  connectionString: string | undefined
): boolean {
  if ((process.env.PGSSLMODE ?? '').toLowerCase() === 'disable') {
    return true
  }
  if (!connectionString) return false

  const parsed = parseConnectionString(connectionString)
  if (!parsed) {
    return connectionString.toLowerCase().includes('sslmode=disable')
  }

  const sslMode = parsed.searchParams.get('sslmode')?.toLowerCase()
  if (sslMode === 'disable') return true

  const hostname = parsed.hostname.toLowerCase()
  return LOCAL_DB_HOSTS.has(hostname)
}

function resolveSslOption(
  connectionString: string | undefined
): PgSslOption {
  return shouldDisableSsl(connectionString)
    ? false
    : { rejectUnauthorized: false }
}

const resolvedConnectionString = resolveConnectionString()

const pool =
  globalDb.__zincDbPool ??
  new Pool({
    connectionString: resolvedConnectionString,
    ssl: resolveSslOption(resolvedConnectionString),
    max: Number(process.env.PGPOOL_MAX ?? 2),
    idleTimeoutMillis: Number(process.env.PGPOOL_IDLE_TIMEOUT_MS ?? 5_000),
    connectionTimeoutMillis: Number(
      process.env.PGPOOL_CONNECT_TIMEOUT_MS ?? 10_000
    ),
    application_name: process.env.PGAPPNAME ?? 'zinc-frontend',
  })

if (!globalDb.__zincDbPool) {
  globalDb.__zincDbPool = pool
}

/* ------------------------------------------------------------------ */
/*  Retry-aware connect                                                */
/* ------------------------------------------------------------------ */

const MAX_RETRIES = Number(process.env.PGPOOL_CONNECT_RETRIES ?? 3)
const BASE_DELAY_MS = 500

function assertDbConfigured(): void {
  if (resolvedConnectionString) return
  throw new Error(
    'Database URL is not configured. Set DATABASE_URL, POSTGRES_URL, or DIRECT_DATABASE_URL.'
  )
}

function isRetryableConnectionError(err: unknown): boolean {
  if (typeof err !== 'object' || err === null) return true
  const candidate = err as { code?: string; message?: string }
  const code = candidate.code
  if (code) {
    if (
      code === 'ECONNREFUSED' ||
      code === 'ETIMEDOUT' ||
      code === 'ECONNRESET' ||
      code === 'EHOSTUNREACH' ||
      code === 'ENETUNREACH'
    ) {
      return true
    }
    if (
      code === '28P01' ||
      code === '28000' ||
      code === '3D000' ||
      code === '3F000'
    ) {
      return false
    }
  }

  const message = (candidate.message ?? '').toLowerCase()
  if (message.includes('does not support ssl connections')) return false
  if (message.includes('password authentication failed')) return false
  if (message.includes('no pg_hba.conf entry')) return false
  if (message.includes('database "') && message.includes('" does not exist')) {
    return false
  }

  return true
}

async function connectWithRetry(): Promise<PoolClient> {
  assertDbConfigured()
  let lastError: unknown
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await pool.connect()
    } catch (err) {
      lastError = err
      if (!isRetryableConnectionError(err)) {
        throw err
      }
      if (attempt < MAX_RETRIES) {
        const delay = BASE_DELAY_MS * 2 ** (attempt - 1) // 500, 1000, 2000
        console.warn(
          `[db] connect attempt ${attempt}/${MAX_RETRIES} failed, retrying in ${delay}ms…`,
          err instanceof Error ? err.message : err
        )
        await new Promise((r) => setTimeout(r, delay))
      }
    }
  }
  throw lastError
}

/* ------------------------------------------------------------------ */
/*  Public API                                                         */
/* ------------------------------------------------------------------ */

export async function query<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T[]> {
  const client = await connectWithRetry()
  try {
    const result = await client.query(sql, params)
    return result.rows as T[]
  } finally {
    client.release()
  }
}

export function getIngestPool(): Pool {
  return pool
}

export default pool
