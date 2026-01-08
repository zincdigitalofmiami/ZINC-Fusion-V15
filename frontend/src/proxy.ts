import { NextResponse, type NextRequest } from 'next/server'
import { getAuthCookieName, verifyAuthToken } from '@/lib/auth-edge'

const PUBLIC_PATH_PREFIXES = [
  '/_next',
  '/favicon',
  '/api/health',
  '/api/auth',
  '/login',
]

export async function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl

  if (PUBLIC_PATH_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p))) {
    return NextResponse.next()
  }

  if (pathname === '/') {
    return NextResponse.next()
  }

  const token = req.cookies.get(getAuthCookieName())?.value
  if (!token) {
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('next', pathname)
    return NextResponse.redirect(url)
  }

  const payload = await verifyAuthToken(token)
  if (!payload) {
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('next', pathname)
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!.*\\..*).*)'],
}
