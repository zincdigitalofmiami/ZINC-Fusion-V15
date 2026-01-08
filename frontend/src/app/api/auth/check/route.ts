import { NextResponse } from 'next/server'
import { cookies } from 'next/headers'
import { getAuthCookieName, verifyAuthToken } from '@/lib/auth'

export const runtime = 'nodejs'

export async function GET() {
  const cookieStore = await cookies()
  const token = cookieStore.get(getAuthCookieName())?.value

  if (!token) {
    return NextResponse.json({ authenticated: false })
  }

  const payload = verifyAuthToken(token)
  if (!payload) {
    return NextResponse.json({ authenticated: false })
  }

  return NextResponse.json({ authenticated: true })
}
