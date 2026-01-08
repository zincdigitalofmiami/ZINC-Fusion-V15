(globalThis.TURBOPACK || (globalThis.TURBOPACK = [])).push(["chunks/[root-of-the-server]__8df9493b._.js",
"[externals]/node:buffer [external] (node:buffer, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("node:buffer", () => require("node:buffer"));

module.exports = mod;
}),
"[externals]/node:async_hooks [external] (node:async_hooks, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("node:async_hooks", () => require("node:async_hooks"));

module.exports = mod;
}),
"[project]/src/lib/auth-edge.ts [middleware-edge] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "getAuthCookieName",
    ()=>getAuthCookieName,
    "verifyAuthToken",
    ()=>verifyAuthToken
]);
const COOKIE_NAME = 'zf_auth';
function getAuthCookieName() {
    return COOKIE_NAME;
}
function base64urlFromBytes(bytes) {
    let binary = '';
    for(let i = 0; i < bytes.length; i++)binary += String.fromCharCode(bytes[i]);
    return btoa(binary).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
}
function bytesFromBase64url(input) {
    const padLength = (4 - input.length % 4) % 4;
    const padded = input + '='.repeat(padLength);
    const b64 = padded.replace(/-/g, '+').replace(/_/g, '/');
    const binary = atob(b64);
    const bytes = new Uint8Array(binary.length);
    for(let i = 0; i < binary.length; i++)bytes[i] = binary.charCodeAt(i);
    return bytes;
}
function timingSafeEqualBytes(a, b) {
    if (a.length !== b.length) return false;
    let diff = 0;
    for(let i = 0; i < a.length; i++)diff |= a[i] ^ b[i];
    return diff === 0;
}
async function hmacSha256(secret, message) {
    const enc = new TextEncoder();
    const key = await crypto.subtle.importKey('raw', enc.encode(secret), {
        name: 'HMAC',
        hash: 'SHA-256'
    }, false, [
        'sign'
    ]);
    const sig = await crypto.subtle.sign('HMAC', key, enc.encode(message));
    return new Uint8Array(sig);
}
async function verifyAuthToken(token) {
    const secret = process.env.AUTH_SECRET;
    if (!secret) return null;
    const parts = token.split('.');
    if (parts.length !== 2) return null;
    const [payloadB64, sigB64] = parts;
    const expectedSig = await hmacSha256(secret, payloadB64);
    const expectedSigB64 = base64urlFromBytes(expectedSig);
    const providedSig = bytesFromBase64url(sigB64);
    const expectedSigBytes = bytesFromBase64url(expectedSigB64);
    if (!timingSafeEqualBytes(providedSig, expectedSigBytes)) return null;
    try {
        const payloadJson = new TextDecoder().decode(bytesFromBase64url(payloadB64));
        const payload = JSON.parse(payloadJson);
        if (!payload || payload.v !== 1 || typeof payload.iat !== 'number') return null;
        return payload;
    } catch  {
        return null;
    }
}
}),
"[project]/src/middleware.ts [middleware-edge] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "config",
    ()=>config,
    "middleware",
    ()=>middleware
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$esm$2f$api$2f$server$2e$js__$5b$middleware$2d$edge$5d$__$28$ecmascript$29$__$3c$locals$3e$__ = __turbopack_context__.i("[project]/node_modules/next/dist/esm/api/server.js [middleware-edge] (ecmascript) <locals>");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$esm$2f$server$2f$web$2f$exports$2f$index$2e$js__$5b$middleware$2d$edge$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/esm/server/web/exports/index.js [middleware-edge] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$auth$2d$edge$2e$ts__$5b$middleware$2d$edge$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/src/lib/auth-edge.ts [middleware-edge] (ecmascript)");
;
;
const PUBLIC_PATH_PREFIXES = [
    '/_next',
    '/favicon',
    '/api/health',
    '/api/auth',
    '/login'
];
async function middleware(req) {
    const { pathname } = req.nextUrl;
    if (PUBLIC_PATH_PREFIXES.some((p)=>pathname === p || pathname.startsWith(p + '/') || pathname.startsWith(p))) {
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$esm$2f$server$2f$web$2f$exports$2f$index$2e$js__$5b$middleware$2d$edge$5d$__$28$ecmascript$29$__["NextResponse"].next();
    }
    if (pathname === '/') {
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$esm$2f$server$2f$web$2f$exports$2f$index$2e$js__$5b$middleware$2d$edge$5d$__$28$ecmascript$29$__["NextResponse"].next();
    }
    const token = req.cookies.get((0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$auth$2d$edge$2e$ts__$5b$middleware$2d$edge$5d$__$28$ecmascript$29$__["getAuthCookieName"])())?.value;
    if (!token) {
        const url = req.nextUrl.clone();
        url.pathname = '/login';
        url.searchParams.set('next', pathname);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$esm$2f$server$2f$web$2f$exports$2f$index$2e$js__$5b$middleware$2d$edge$5d$__$28$ecmascript$29$__["NextResponse"].redirect(url);
    }
    const payload = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$src$2f$lib$2f$auth$2d$edge$2e$ts__$5b$middleware$2d$edge$5d$__$28$ecmascript$29$__["verifyAuthToken"])(token);
    if (!payload) {
        const url = req.nextUrl.clone();
        url.pathname = '/login';
        url.searchParams.set('next', pathname);
        return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$esm$2f$server$2f$web$2f$exports$2f$index$2e$js__$5b$middleware$2d$edge$5d$__$28$ecmascript$29$__["NextResponse"].redirect(url);
    }
    return __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$esm$2f$server$2f$web$2f$exports$2f$index$2e$js__$5b$middleware$2d$edge$5d$__$28$ecmascript$29$__["NextResponse"].next();
}
const config = {
    matcher: [
        '/((?!.*\\..*).*)'
    ]
};
}),
]);

//# sourceMappingURL=%5Broot-of-the-server%5D__8df9493b._.js.map