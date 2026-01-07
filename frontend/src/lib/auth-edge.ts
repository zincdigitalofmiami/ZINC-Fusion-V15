export type AuthPayload = {
  v: 1
  iat: number
}

const COOKIE_NAME = 'zf_auth'

export function getAuthCookieName() {
  return COOKIE_NAME
}

function base64urlFromBytes(bytes: Uint8Array): string {
  let binary = ''
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i])
  return btoa(binary).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_')
}

function bytesFromBase64url(input: string): Uint8Array {
  const padLength = (4 - (input.length % 4)) % 4
  const padded = input + '='.repeat(padLength)
  const b64 = padded.replace(/-/g, '+').replace(/_/g, '/')
  const binary = atob(b64)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
  return bytes
}

function timingSafeEqualBytes(a: Uint8Array, b: Uint8Array): boolean {
  if (a.length !== b.length) return false
  let diff = 0
  for (let i = 0; i < a.length; i++) diff |= a[i] ^ b[i]
  return diff === 0
}

async function hmacSha256(secret: string, message: string): Promise<Uint8Array> {
  const enc = new TextEncoder()
  const key = await crypto.subtle.importKey(
    'raw',
    enc.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    ['sign']
  )

  const sig = await crypto.subtle.sign('HMAC', key, enc.encode(message))
  return new Uint8Array(sig)
}

export async function verifyAuthToken(token: string): Promise<AuthPayload | null> {
  const secret = process.env.AUTH_SECRET
  if (!secret) return null

  const parts = token.split('.')
  if (parts.length !== 2) return null

  const [payloadB64, sigB64] = parts

  const expectedSig = await hmacSha256(secret, payloadB64)
  const expectedSigB64 = base64urlFromBytes(expectedSig)

  const providedSig = bytesFromBase64url(sigB64)
  const expectedSigBytes = bytesFromBase64url(expectedSigB64)

  if (!timingSafeEqualBytes(providedSig, expectedSigBytes)) return null

  try {
    const payloadJson = new TextDecoder().decode(bytesFromBase64url(payloadB64))
    const payload = JSON.parse(payloadJson) as AuthPayload
    if (!payload || payload.v !== 1 || typeof payload.iat !== 'number') return null
    return payload
  } catch {
    return null
  }
}
