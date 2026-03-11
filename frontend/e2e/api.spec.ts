/**
 * API endpoint smoke tests for ZINC-FUSION-V15 frontend.
 *
 * Tests every GET endpoint for:
 *   - HTTP 200 (or expected status)
 *   - Valid JSON response
 *   - Expected top-level keys present
 *   - Parameter validation where applicable
 *
 * Auth endpoints tested for login/logout flow.
 * All tests are read-only — no data mutation.
 * CRITICAL: never call POST /api/vegas/sync from this suite.
 */
import { test, expect, type APIRequestContext } from "@playwright/test";

// ── Helpers ──────────────────────────────────────────────────────────────────

/** GET a JSON endpoint and assert status is among `okStatuses`. */
async function getJson(
  request: APIRequestContext,
  path: string,
  okStatuses: number[] = [200],
): Promise<{ status: number; body: Record<string, unknown> }> {
  const res = await request.get(path);
  const status = res.status();
  expect(okStatuses).toContain(status);
  const body = (await res.json()) as Record<string, unknown>;
  return { status, body };
}

/** Assert `body` contains each key (and optional value). */
function expectKeys(
  body: Record<string, unknown>,
  keys: (string | [string, unknown])[],
): void {
  for (const k of keys) {
    if (Array.isArray(k)) {
      expect(body).toHaveProperty(k[0], k[1]);
    } else {
      expect(body).toHaveProperty(k);
    }
  }
}

/** Assert a property is an array. */
function expectArray(body: Record<string, unknown>, key: string): void {
  expect(Array.isArray(body[key])).toBe(true);
}

// ── Data-driven endpoint table ───────────────────────────────────────────────

interface EndpointSpec {
  path: string;
  okStatuses?: number[];
  requiredKeys?: (string | [string, unknown])[];
  arrayKeys?: string[];
}

const ZL_ENDPOINTS: EndpointSpec[] = [
  {
    path: "/api/zl/live",
    requiredKeys: [["symbol", "ZL"], "price", "timestamp"],
  },
  {
    path: "/api/zl/chart?days=30",
    requiredKeys: [["symbol", "ZL"], "series", "count"],
    arrayKeys: ["series"],
  },
  {
    path: "/api/zl/price-1d?days=7",
    okStatuses: [200, 404],
    requiredKeys: [["symbol", "ZL"], "data", ["interval", "1d"]],
    arrayKeys: ["data"],
  },
  {
    path: "/api/zl/price-1h?hours=24",
    okStatuses: [200, 404],
    requiredKeys: [["symbol", "ZL"], "data"],
    arrayKeys: ["data"],
  },
  {
    path: "/api/zl/price-5m?hours=1",
    okStatuses: [200, 404],
    requiredKeys: [["symbol", "ZL"], "data", ["requested_interval", "5m"]],
  },
  {
    path: "/api/zl/price-1m?minutes=60",
    okStatuses: [200, 404],
    requiredKeys: [["symbol", "ZL"]],
  },
  {
    path: "/api/zl/intraday?hours=1",
    requiredKeys: [["symbol", "ZL"], "bars"],
    arrayKeys: ["bars"],
  },
  {
    path: "/api/zl/raw?days=7",
    requiredKeys: [["symbol", "ZL"], ["source", "mkt.futures_1d"], "data"],
    arrayKeys: ["data"],
  },
  {
    path: "/api/zl/forecast",
    okStatuses: [200, 404],
    requiredKeys: [["symbol", "ZL"], "forecasts"],
    arrayKeys: ["forecasts"],
  },
  {
    path: "/api/zl/forecast-targets",
    requiredKeys: [["symbol", "ZL"], "targets"],
    arrayKeys: ["targets"],
  },
];

// ── Tests ────────────────────────────────────────────────────────────────────

test.describe("Health", () => {
  test("GET /api/health — ok:true", async ({ request }) => {
    const { body } = await getJson(request, "/api/health");
    expect(body).toHaveProperty("ok", true);
  });
});

test.describe("Auth", () => {
  test("GET /api/auth/check — returns authenticated boolean", async ({
    request,
  }) => {
    const { body } = await getJson(request, "/api/auth/check");
    expectKeys(body, ["authenticated"]);
    expect(typeof body.authenticated).toBe("boolean");
  });

  test("POST /api/auth/login — missing password → 400", async ({
    request,
  }) => {
    const res = await request.post("/api/auth/login", { data: {} });
    expect(res.status()).toBe(400);
    expect((await res.json()).ok).toBe(false);
  });

  test("POST /api/auth/login — wrong password → 401", async ({ request }) => {
    const res = await request.post("/api/auth/login", {
      data: { password: "definitely-wrong-password-12345" },
    });
    expect(res.status()).toBe(401);
    expect((await res.json()).ok).toBe(false);
  });

  test("POST /api/auth/logout — ok:true", async ({ request }) => {
    const res = await request.post("/api/auth/logout");
    expect(res.status()).toBe(200);
    expect((await res.json()).ok).toBe(true);
  });
});

test.describe("ZL data endpoints", () => {
  for (const spec of ZL_ENDPOINTS) {
    test(`GET ${spec.path}`, async ({ request }) => {
      const statuses = spec.okStatuses ?? [200];
      const { status, body } = await getJson(request, spec.path, statuses);

      if (status === 200 && spec.requiredKeys) {
        expectKeys(body, spec.requiredKeys);
      }
      if (status === 200 && spec.arrayKeys) {
        for (const k of spec.arrayKeys) expectArray(body, k);
      }
      if (status !== 200) {
        expect("error" in body || "forecasts" in body).toBe(true);
      }
    });
  }
});

test.describe("Brief", () => {
  test("GET /api/zl/brief — returns brief or 503", async ({ request }) => {
    const { status, body } = await getJson(request, "/api/zl/brief", [
      200, 503,
    ]);
    if (status === 200) {
      expectKeys(body, ["generatedAt", "price", "recommendation"]);
    }
  });
});

test.describe("Market analysis", () => {
  test("GET /api/market-drivers", async ({ request }) => {
    const { status, body } = await getJson(request, "/api/market-drivers", [
      200, 503,
    ]);
    if (status === 200) {
      expectKeys(body, ["drivers", "summary", "as_of_date"]);
    }
  });

  test("GET /api/epu — defaults", async ({ request }) => {
    const { body } = await getJson(request, "/api/epu");
    expectKeys(body, ["meta", "data", "summary"]);
    expectArray(body, "data");
  });

  test("GET /api/epu — query params", async ({ request }) => {
    const { body } = await getJson(
      request,
      "/api/epu?days=30&series=us&include_vix=false",
    );
    expect((body.meta as Record<string, unknown>).days_requested).toBe(30);
  });

  test("GET /api/options — valid request", async ({ request }) => {
    const { body } = await getJson(request, "/api/options?days=7&limit=10");
    expectKeys(body, [["underlying", "ZL"], "data"]);
    expectArray(body, "data");
  });

  test("GET /api/options — invalid underlying → 400", async ({ request }) => {
    const { body } = await getJson(
      request,
      "/api/options?underlying=INVALID!!!",
      [400],
    );
    expectKeys(body, ["error"]);
  });
});

test.describe("Sentiment", () => {
  test("GET /api/sentiment/cot", async ({ request }) => {
    const { status, body } = await getJson(request, "/api/sentiment/cot", [
      200, 404,
    ]);
    if (status === 200) {
      expectKeys(body, [["symbol", "ZL"], "latest", "history"]);
    }
  });

  test("GET /api/sentiment/news", async ({ request }) => {
    const { body } = await getJson(request, "/api/sentiment/news");
    expectKeys(body, ["headlines", "stats"]);
    expectArray(body, "headlines");
  });

  for (const [path, statuses] of [
    ["/api/sentiment/metrics", [200, 500]],
    ["/api/sentiment/narrative", [200, 405, 500]],
    ["/api/sentiment/topics", [200, 500]],
  ] as const) {
    test(`GET ${path}`, async ({ request }) => {
      await getJson(request, path, [...statuses]);
    });
  }
});

test.describe("Vegas", () => {
  test("GET /api/vegas — stats view", async ({ request }) => {
    const { body } = await getJson(request, "/api/vegas");
    expectKeys(body, ["restaurants", "casinos", "fryers"]);
  });

  test("GET /api/vegas?view=restaurants", async ({ request }) => {
    const { body } = await getJson(request, "/api/vegas?view=restaurants");
    expectKeys(body, ["restaurants", "count"]);
  });

  test("GET /api/vegas?view=events", async ({ request }) => {
    const { body } = await getJson(request, "/api/vegas?view=events");
    expectKeys(body, ["events", "count"]);
  });

  test("GET /api/vegas?view=zfusion — missing eventId → 400", async ({
    request,
  }) => {
    const { body } = await getJson(request, "/api/vegas?view=zfusion", [400]);
    expectKeys(body, ["error"]);
  });

  for (const [path, statuses] of [
    ["/api/vegas/fryers", [200, 500]],
    ["/api/vegas/restaurants", [200, 500]],
  ] as const) {
    test(`GET ${path}`, async ({ request }) => {
      await getJson(request, path, [...statuses]);
    });
  }

  test("GET /api/vegas/sync — metadata only (no sync side effects)", async ({
    request,
  }) => {
    const { body } = await getJson(request, "/api/vegas/sync", [200]);
    expectKeys(body, [
      ["endpoint", "/api/vegas/sync"],
      ["method", "POST to queue a manual sync event"],
      "tables",
    ]);
    expectArray(body, "tables");
    expect(body).not.toHaveProperty("success");
    expect(body).not.toHaveProperty("results");
  });
});

test.describe("Misc", () => {
  test("GET /api/quant/overview — 200 or 410", async ({ request }) => {
    await getJson(request, "/api/quant/overview", [200, 410]);
  });

  test("GET /api/refresh-drivers — 200 or 503", async ({ request }) => {
    await getJson(request, "/api/refresh-drivers", [200, 503]);
  });

  test("GET /api/inngest — introspection", async ({ request }) => {
    await getJson(request, "/api/inngest", [200, 204, 500]);
  });
});
