/**
 * Database client for Prisma Postgres
 * Queries institutional schema tables (mkt.*, econ.*, features.*, etc.) at runtime
 */
import { Pool } from 'pg'

type GlobalDbPool = {
  __zincDbPool?: Pool
}

const globalDb = globalThis as unknown as GlobalDbPool

const pool =
  globalDb.__zincDbPool ??
  new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false },
    // Keep pool conservative for serverless/edge fanout.
    max: Number(process.env.PGPOOL_MAX ?? 4),
    idleTimeoutMillis: Number(process.env.PGPOOL_IDLE_TIMEOUT_MS ?? 10000),
    connectionTimeoutMillis: Number(process.env.PGPOOL_CONNECT_TIMEOUT_MS ?? 5000),
    application_name: process.env.PGAPPNAME ?? 'zinc-frontend',
  })

if (!globalDb.__zincDbPool) {
  globalDb.__zincDbPool = pool
}

export async function query<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T[]> {
  const client = await pool.connect()
  try {
    const result = await client.query(sql, params)
    return result.rows as T[]
  } finally {
    client.release()
  }
}

export default pool
