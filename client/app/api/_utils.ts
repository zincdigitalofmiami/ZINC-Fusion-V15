import { NextRequest } from "next/server";

const DEFAULT_API_BASE = "http://127.0.0.1:8000";

export function fusionApiBase(): string {
  return (
    process.env.FUSION_API_BASE ||
    process.env.NEXT_PUBLIC_API_BASE ||
    DEFAULT_API_BASE
  );
}

function isLocalhostBase(base: string) {
  return (
    base.includes("127.0.0.1") ||
    base.includes("localhost") ||
    base.startsWith("http://0.0.0.0")
  );
}

function isNonLocalRequest(request: NextRequest) {
  const host = request.headers.get("host") || "";
  return !host.startsWith("localhost") && !host.startsWith("127.0.0.1");
}

function copyHeader(headers: Headers, upstream: Headers, name: string) {
  const value = upstream.get(name);
  if (value) headers.set(name, value);
}

export async function proxyToFusionApi(
  request: NextRequest,
  upstreamPath: string,
): Promise<Response> {
  const base = fusionApiBase();
  if (isLocalhostBase(base) && isNonLocalRequest(request)) {
    return new Response(
      JSON.stringify({
        detail:
          "Backend API base is not configured. Set NEXT_PUBLIC_API_BASE (or FUSION_API_BASE) to your deployed fusion-api URL.",
        hint:
          "Example: NEXT_PUBLIC_API_BASE=https://api.yourdomain.com (must serve /health and /api/*).",
        current_base: base,
      }),
      { status: 500, headers: { "content-type": "application/json" } },
    );
  }

  const upstreamUrl = new URL(upstreamPath, fusionApiBase());
  upstreamUrl.search = request.nextUrl.search;

  const upstreamResponse = await fetch(upstreamUrl, {
    method: "GET",
    headers: {
      accept: request.headers.get("accept") || "application/json",
    },
    cache: "no-store",
  });

  const responseHeaders = new Headers();
  copyHeader(responseHeaders, upstreamResponse.headers, "content-type");
  copyHeader(responseHeaders, upstreamResponse.headers, "cache-control");

  return new Response(await upstreamResponse.arrayBuffer(), {
    status: upstreamResponse.status,
    headers: responseHeaders,
  });
}
