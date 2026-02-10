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

const pool =
  globalDb.__zincDbPool ??
  new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false },
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

async function connectWithRetry(): Promise<PoolClient> {
  let lastError: unknown
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await pool.connect()
    } catch (err) {
      lastError = err
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

export default pool
