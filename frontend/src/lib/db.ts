/**
 * Database client for cloud/local Postgres.
 * Default behavior is cloud-only for backward compatibility.
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

type QueryRouteTarget = 'auto' | 'cloud' | 'local'
type QueryPurpose = 'read' | 'write'

export type QueryRouteOpts = {
  target?: QueryRouteTarget
  purpose?: QueryPurpose
  allowCloudFallback?: boolean
  routeTag?: string
}

type GlobalDbPools = {
  __zincDbPool?: Pool
  __zincLocalDbPool?: Pool
}

const globalDb = globalThis as unknown as GlobalDbPools

const isVercelRuntime = process.env.VERCEL === '1'
const routingMode = process.env.DB_ROUTING_MODE ?? 'cloud_only'
const localRoutingEnabled = routingMode === 'dual' && !isVercelRuntime
const expectedLocalDbName =
  process.env.LOCAL_DB_EXPECTED_NAME ?? 'zinc_fusion_v15_local'

function parseDbIdentityFromUrl(url: string): { host: string; dbName: string } {
  let parsed: URL
  try {
    parsed = new URL(url)
  } catch (error) {
    throw new Error(
      `[db] Invalid LOCAL_DATABASE_URL: ${error instanceof Error ? error.message : String(error)}`
    )
  }

  const dbName = parsed.pathname.replace(/^\//, '')
  return { host: parsed.hostname, dbName }
}

function assertLocalDbIdentity(): void {
  if (!localRoutingEnabled) return

  const localUrl = process.env.LOCAL_DATABASE_URL
  if (!localUrl) {
    throw new Error('[db] LOCAL_DATABASE_URL is required when DB_ROUTING_MODE=dual.')
  }

  const { host, dbName } = parseDbIdentityFromUrl(localUrl)
  const allowedHosts = new Set(['localhost', '127.0.0.1', '::1'])
  if (!allowedHosts.has(host)) {
    throw new Error(
      `[db] LOCAL_DATABASE_URL must target local host (${[...allowedHosts].join(', ')}); got '${host}'.`
    )
  }

  if (dbName !== expectedLocalDbName) {
    throw new Error(
      `[db] LOCAL_DATABASE_URL must use database '${expectedLocalDbName}', got '${dbName || '<empty>'}'.`
    )
  }
}

assertLocalDbIdentity()

const cloudPool =
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
  globalDb.__zincDbPool = cloudPool
}

function getLocalPool(): Pool {
  if (isVercelRuntime) {
    throw new Error(
      '[db] Local DB routing is disabled on Vercel runtime; use cloud pool.'
    )
  }
  if (routingMode !== 'dual') {
    throw new Error('[db] Local DB routing requires DB_ROUTING_MODE=dual.')
  }
  if (!process.env.LOCAL_DATABASE_URL) {
    throw new Error(
      '[db] LOCAL_DATABASE_URL is required when DB_ROUTING_MODE=dual.'
    )
  }

  if (!globalDb.__zincLocalDbPool) {
    globalDb.__zincLocalDbPool = new Pool({
      connectionString: process.env.LOCAL_DATABASE_URL,
      ssl: false,
      max: Number(process.env.LOCAL_PGPOOL_MAX ?? 20),
      idleTimeoutMillis: Number(
        process.env.LOCAL_PGPOOL_IDLE_TIMEOUT_MS ?? 5_000
      ),
      connectionTimeoutMillis: Number(
        process.env.LOCAL_PGPOOL_CONNECT_TIMEOUT_MS ?? 10_000
      ),
      application_name: process.env.PGAPPNAME_LOCAL ?? 'zinc-frontend-local',
    })
  }

  return globalDb.__zincLocalDbPool
}

/* ------------------------------------------------------------------ */
/*  Retry-aware connect                                                */
/* ------------------------------------------------------------------ */

const MAX_RETRIES = Number(process.env.PGPOOL_CONNECT_RETRIES ?? 3)
const BASE_DELAY_MS = 500

async function connectWithRetry(
  targetPool: Pool,
  targetLabel: 'cloud' | 'local'
): Promise<PoolClient> {
  let lastError: unknown
  for (let attempt = 1; attempt <= MAX_RETRIES; attempt++) {
    try {
      return await targetPool.connect()
    } catch (err) {
      lastError = err
      if (attempt < MAX_RETRIES) {
        const delay = BASE_DELAY_MS * 2 ** (attempt - 1) // 500, 1000, 2000
        console.warn(
          `[db:${targetLabel}] connect attempt ${attempt}/${MAX_RETRIES} failed, retrying in ${delay}ms…`,
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

function extractSchemaName(sql: string): string | null {
  const normalized = sql.replace(/\s+/g, ' ').trim()
  const match =
    normalized.match(/\b(?:FROM|JOIN|INTO|UPDATE|TABLE|DELETE FROM)\s+([a-z_][a-z0-9_]*)\./i) ??
    normalized.match(/\bTRUNCATE\s+TABLE\s+([a-z_][a-z0-9_]*)\./i)

  return match?.[1]?.toLowerCase() ?? null
}

function resolveRouteTarget(sql: string, opts?: QueryRouteOpts): 'cloud' | 'local' {
  const explicitTarget = opts?.target ?? 'auto'

  if (explicitTarget === 'cloud') return 'cloud'
  if (explicitTarget === 'local') return 'local'

  if (!localRoutingEnabled) return 'cloud'

  const schema = extractSchemaName(sql)
  const localSchemas = new Set(
    (process.env.LOCAL_ROUTE_SCHEMAS ?? 'ops')
      .split(',')
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean)
  )

  return schema && localSchemas.has(schema) ? 'local' : 'cloud'
}

function maybeLogRoute(target: 'cloud' | 'local', opts?: QueryRouteOpts): void {
  if (process.env.DB_ROUTE_LOG !== '1') return
  console.info(`[db:route] target=${target} mode=${routingMode} tag=${opts?.routeTag ?? 'none'}`)
}

export async function queryCloud<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T[]> {
  const client = await connectWithRetry(cloudPool, 'cloud')
  try {
    const result = await client.query(sql, params)
    return result.rows as T[]
  } finally {
    client.release()
  }
}

export async function queryLocal<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T[]> {
  const client = await connectWithRetry(getLocalPool(), 'local')
  try {
    const result = await client.query(sql, params)
    return result.rows as T[]
  } finally {
    client.release()
  }
}

export async function queryRouted<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[],
  opts?: QueryRouteOpts
): Promise<T[]> {
  const target = resolveRouteTarget(sql, opts)
  maybeLogRoute(target, opts)

  if (target === 'cloud') {
    return queryCloud<T>(sql, params)
  }

  try {
    return await queryLocal<T>(sql, params)
  } catch (error) {
    if (opts?.allowCloudFallback) {
      console.warn('[db:route] local query failed, falling back to cloud', {
        error: error instanceof Error ? error.message : String(error),
        tag: opts.routeTag ?? null,
      })
      return queryCloud<T>(sql, params)
    }
    throw error
  }
}

export async function query<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T[]> {
  return queryCloud<T>(sql, params)
}

export async function withCloudClient<T>(
  fn: (client: PoolClient) => Promise<T>
): Promise<T> {
  const client = await connectWithRetry(cloudPool, 'cloud')
  try {
    return await fn(client)
  } finally {
    client.release()
  }
}

export async function withLocalClient<T>(
  fn: (client: PoolClient) => Promise<T>
): Promise<T> {
  const client = await connectWithRetry(getLocalPool(), 'local')
  try {
    return await fn(client)
  } finally {
    client.release()
  }
}

export function getIngestPool(): Pool {
  if (routingMode === 'dual' && !isVercelRuntime) {
    return getLocalPool()
  }
  return cloudPool
}

export const localRoutingConfig = {
  mode: routingMode,
  enabled: localRoutingEnabled,
  isVercelRuntime,
}

export default cloudPool
