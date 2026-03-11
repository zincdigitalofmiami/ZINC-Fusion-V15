import { resolveConnectionStringFromEnv } from '@/lib/db-env'

type EnvMap = Record<string, string | undefined>

const LOCAL_DB_HOSTS = new Set([
  'localhost',
  '127.0.0.1',
  '::1',
  '0.0.0.0',
  'host.docker.internal',
])

function isLocalConnectionString(connectionString: string | undefined): boolean {
  if (!connectionString) return false
  try {
    const parsed = new URL(connectionString)
    return LOCAL_DB_HOSTS.has(parsed.hostname.toLowerCase())
  } catch {
    const lower = connectionString.toLowerCase()
    return (
      lower.includes('localhost') ||
      lower.includes('127.0.0.1') ||
      lower.includes('host.docker.internal')
    )
  }
}

/**
 * Vegas sync is cloud-only by default.
 * - Block all non-Vercel runtime usage (local/dev machines).
 * - Also block if DB target resolves to localhost.
 * - Allow explicit emergency override via ALLOW_LOCAL_VEGAS_SYNC=1.
 */
export function isVegasSyncBlocked(
  env: EnvMap = process.env as EnvMap
): boolean {
  if ((env.ALLOW_LOCAL_VEGAS_SYNC ?? '').trim() === '1') return false

  const isVercelRuntime = env.VERCEL === '1'
  if (!isVercelRuntime) return true

  return isLocalConnectionString(resolveConnectionStringFromEnv(env))
}
