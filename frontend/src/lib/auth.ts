import crypto from 'crypto'

const COOKIE_NAME = 'zf_auth'

function base64urlEncode(input: Buffer | string): string {
  const buffer = Buffer.isBuffer(input) ? input : Buffer.from(input)
  return buffer
    .toString('base64')
    .replace(/=/g, '')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
}

function base64urlDecode(input: string): Buffer {
  const padLength = (4 - (input.length % 4)) % 4
  const padded = input + '='.repeat(padLength)
  const b64 = padded.replace(/-/g, '+').replace(/_/g, '/')
  return Buffer.from(b64, 'base64')
}

function timingSafeEqual(a: string, b: string): boolean {
  const aBuf = Buffer.from(a)
  const bBuf = Buffer.from(b)
  if (aBuf.length !== bBuf.length) return false
  return crypto.timingSafeEqual(aBuf, bBuf)
}

export type AuthPayload = {
  v: 1
  iat: number
}

export function getAuthEnv() {
  const password = process.env.AUTH_PASSWORD
  const secret = process.env.AUTH_SECRET

  if (!password) {
    throw new Error('Missing AUTH_PASSWORD env var')
  }
  if (!secret) {
    throw new Error('Missing AUTH_SECRET env var')
  }

  return { password, secret }
}

export function getAuthCookieName() {
  return COOKIE_NAME
}

export function verifyPassword(inputPassword: string) {
  const { password } = getAuthEnv()
  return timingSafeEqual(inputPassword, password)
}

export function signAuthToken(payload: AuthPayload) {
  const { secret } = getAuthEnv()

  const payloadJson = JSON.stringify(payload)
  const payloadB64 = base64urlEncode(payloadJson)

  const sig = crypto.createHmac('sha256', secret).update(payloadB64).digest()
  const sigB64 = base64urlEncode(sig)

  return `${payloadB64}.${sigB64}`
}

const MAX_TOKEN_AGE_S = 30 * 24 * 60 * 60 // 30 days — matches cookie maxAge

export function verifyAuthToken(token: string): AuthPayload | null {
  const { secret } = getAuthEnv()

  const parts = token.split('.')
  if (parts.length !== 2) return null

  const [payloadB64, sigB64] = parts

  const expectedSig = crypto.createHmac('sha256', secret).update(payloadB64).digest()
  const expectedSigB64 = base64urlEncode(expectedSig)

  if (!timingSafeEqual(sigB64, expectedSigB64)) return null

  try {
    const payload = JSON.parse(base64urlDecode(payloadB64).toString('utf8')) as AuthPayload
    if (!payload || payload.v !== 1 || typeof payload.iat !== 'number') return null
    // Reject expired tokens
    if (Date.now() / 1000 - payload.iat > MAX_TOKEN_AGE_S) return null
    return payload
  } catch {
    return null
  }
}
