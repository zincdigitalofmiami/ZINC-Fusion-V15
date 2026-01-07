import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { getAuthCookieName, signAuthToken, verifyPassword } from '@/lib/auth'

export const runtime = 'nodejs'

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as null | { password?: string }
  const password = body?.password

  if (!password || typeof password !== 'string') {
    return NextResponse.json({ ok: false, error: 'Missing password' }, { status: 400 })
  }

  if (!verifyPassword(password)) {
    return NextResponse.json({ ok: false, error: 'Invalid password' }, { status: 401 })
  }

  const token = signAuthToken({ v: 1, iat: Math.floor(Date.now() / 1000) })
  const isProd = process.env.NODE_ENV === 'production'

  const cookieStore = await cookies()

  cookieStore.set({
    name: getAuthCookieName(),
    value: token,
    httpOnly: true,
    secure: isProd,
    sameSite: 'lax',
    path: '/',
    maxAge: 60 * 60 * 24 * 30,
  })

  return NextResponse.json({ ok: true })
}
