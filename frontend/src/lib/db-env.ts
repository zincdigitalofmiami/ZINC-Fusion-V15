type EnvMap = Record<string, string | undefined>

export function resolveConnectionStringFromEnv(
  env: EnvMap = process.env as EnvMap
): string | undefined {
  const raw = (env.DATABASE_URL ?? '').trim()
  if (!raw) return undefined
  if (raw.startsWith('prisma+postgres://')) {
    throw new Error(
      'DATABASE_URL must be a direct postgres:// or postgresql:// URL for pg runtime access.'
    )
  }
  return raw
}

export function hasDatabaseConfig(
  env: EnvMap = process.env as EnvMap
): boolean {
  return Boolean(resolveConnectionStringFromEnv(env))
}
