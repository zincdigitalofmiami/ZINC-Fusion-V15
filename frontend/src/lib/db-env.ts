const DB_URL_KEYS = [
  'DATABASE_URL',
  'POSTGRES_URL',
  'DIRECT_DATABASE_URL',
] as const

type EnvMap = Record<string, string | undefined>

export function resolveConnectionStringFromEnv(
  env: EnvMap = process.env as EnvMap
): string | undefined {
  for (const key of DB_URL_KEYS) {
    const value = env[key]
    if (!value) continue
    const trimmed = value.trim()
    if (trimmed.length > 0) return trimmed
  }
  return undefined
}

export function hasDatabaseConfig(
  env: EnvMap = process.env as EnvMap
): boolean {
  return Boolean(resolveConnectionStringFromEnv(env))
}
