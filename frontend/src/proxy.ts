import { NextResponse, type NextRequest } from 'next/server'
import { getAuthCookieName, verifyAuthToken } from '@/lib/auth-edge'

const PUBLIC_PATH_PREFIXES = [
  '/_next',
  '/favicon',
  '/api/health',
  '/api/auth',
  '/api/inngest',  // Public - Inngest handles its own auth via signing key
  '/login',
]

export async function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl

  // Allow public paths
  if (PUBLIC_PATH_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p))) {
    return NextResponse.next()
  }

  // Allow home page
  if (pathname === '/') {
    return NextResponse.next()
  }

  // Check for auth token
  const token = req.cookies.get(getAuthCookieName())?.value
  if (!token) {
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('next', pathname)
    return NextResponse.redirect(url)
  }

  // Verify token
  const payload = await verifyAuthToken(token)
  if (!payload) {
    // Invalid token - clear it and redirect to login
    const url = req.nextUrl.clone()
    url.pathname = '/login'
    url.searchParams.set('next', pathname)
    const response = NextResponse.redirect(url)
    response.cookies.delete(getAuthCookieName())
    return response
  }

  return NextResponse.next()
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public files (public folder)
     */
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)',
  ],
}
