import { cookies } from 'next/headers'
import { NextResponse } from 'next/server'
import { getAuthCookieName } from '@/lib/auth'

export const runtime = 'nodejs'

export async function POST() {
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

  return NextResponse.json({ ok: true })
}
