/**
 * Auth proxy — protects pages (redirect to /login) AND API routes (401).
 *
 * Uses Edge-compatible HMAC-SHA256 verification from auth-edge.ts.
 *
 * Fully public (no auth):
 *   /_next/*, /favicon*, /login, /
 *   /api/auth/*      — login / logout / check
 *   /api/health      — uptime probe
 *
 * Auth-gated API routes return 401 JSON for unauthenticated requests.
 * Auth-gated pages redirect to /login.
 */
import { NextResponse, type NextRequest } from "next/server";
import { getAuthCookieName, verifyAuthToken } from "@/lib/auth-edge";

// ── Routes that need zero auth ─────────────────────────────────────────
const FULLY_PUBLIC_PREFIXES = [
  "/_next",
  "/favicon",
  "/api/health",
  "/api/auth",
  "/login",
];

const MAX_TOKEN_AGE_S = 30 * 24 * 60 * 60; // 30 days — matches cookie maxAge

function isFullyPublic(pathname: string): boolean {
  if (pathname === "/") return true;
  return FULLY_PUBLIC_PREFIXES.some(
    (p) => pathname === p || pathname.startsWith(p + "/") || pathname.startsWith(p),
  );
}

// ── Token verification (shared by API and page gates) ──────────────────
async function verifyRequest(
  req: NextRequest,
): Promise<{ valid: true } | { valid: false; expired?: boolean }> {
  const token = req.cookies.get(getAuthCookieName())?.value;
  if (!token) return { valid: false };

  const payload = await verifyAuthToken(token);
  if (!payload) return { valid: false };

  // Reject expired tokens
  const ageSeconds = Date.now() / 1000 - payload.iat;
  if (ageSeconds > MAX_TOKEN_AGE_S) return { valid: false, expired: true };

  return { valid: true };
}

// ── Main proxy ─────────────────────────────────────────────────────────
export async function proxy(req: NextRequest) {
  const { pathname } = req.nextUrl;

  // Fully public — no auth needed
  if (isFullyPublic(pathname)) {
    return NextResponse.next();
  }

  const auth = await verifyRequest(req);

  // ── API routes: return 401 JSON ────────────────────────────────────
  if (pathname.startsWith("/api/")) {
    if (!auth.valid) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }
    return NextResponse.next();
  }

  // ── Page routes: redirect to /login ────────────────────────────────
  if (!auth.valid) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    const response = NextResponse.redirect(url);
    // Clear stale/invalid cookie
    response.cookies.delete(getAuthCookieName());
    return response;
  }

  return NextResponse.next();
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
    "/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp)$).*)",
  ],
};
