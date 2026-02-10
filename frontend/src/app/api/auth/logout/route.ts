import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { getAuthCookieName } from '@/lib/auth'

export const runtime = 'nodejs'

async function clearAuthCookie() {
  const cookieStore = await cookies()

  cookieStore.set({
    name: getAuthCookieName(),
    value: '',
    httpOnly: true,
    secure: process.env.NODE_ENV === 'production',
    sameSite: 'lax',
    path: '/',
    maxAge: 0,
  })
}

export async function POST() {
  await clearAuthCookie()
  return NextResponse.json({ ok: true })
}

// Also support GET for direct navigation
export async function GET(request: Request) {
  await clearAuthCookie()

  const url = new URL(request.url)
  const redirectUrl = new URL('/login', url.origin)

  return NextResponse.redirect(redirectUrl, { status: 302 })
}
