import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/db", () => ({
  query: vi.fn(),
}));

vi.mock("@/inngest/client", () => ({
  inngest: {
    send: vi.fn(),
  },
}));

process.env.REFRESH_DRIVERS_ALLOW_MEMORY_GATE_FALLBACK = "false";

import { query } from "@/lib/db";
import { inngest } from "@/inngest/client";
import { POST } from "./route";

const queryMock = vi.mocked(query);
const sendMock = vi.mocked(inngest.send);

describe("POST /api/refresh-drivers", () => {
  beforeEach(() => {
    queryMock.mockReset();
    sendMock.mockReset();
  });

  it("returns 503 when DB gate is unavailable and memory fallback is disabled", async () => {
    queryMock.mockRejectedValueOnce(new Error("db unavailable"));

    const res = await POST();
    const body = await res.json();

    expect(res.status).toBe(503);
    expect(body.status).toBe("gate_unavailable");
    expect(body.gateMode).toBe("unavailable");
    expect(sendMock).not.toHaveBeenCalled();
  });

  it("returns 429 when DB gate reports lock contention", async () => {
    queryMock.mockResolvedValueOnce([{ lock_acquired: false, id: null }] as never);

    const res = await POST();
    const body = await res.json();

    expect(res.status).toBe(429);
    expect(body.status).toBe("rate_limited");
    expect(body.gateMode).toBe("db");
    expect(body.reason).toBe("busy");
    expect(sendMock).not.toHaveBeenCalled();
  });

  it("dispatches refresh jobs when DB gate grants access and records completion", async () => {
    queryMock
      .mockResolvedValueOnce([{ lock_acquired: true, id: "run-1" }] as never)
      .mockResolvedValueOnce([] as never);
    sendMock.mockResolvedValue({ id: "evt-1" } as never);

    const res = await POST();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.status).toBe("success");
    expect(body.gateMode).toBe("db");
    expect(sendMock).toHaveBeenCalledTimes(5);
    expect(queryMock).toHaveBeenCalledTimes(2);
    expect(String(queryMock.mock.calls[0]?.[0])).toContain(
      "pg_try_advisory_xact_lock",
    );
  });

  it("allows only one winner in concurrent requests when DB lock result differs", async () => {
    let acquireCalls = 0;
    queryMock.mockImplementation(async (sql: string) => {
      if (sql.includes("pg_try_advisory_xact_lock")) {
        acquireCalls += 1;
        if (acquireCalls === 1) {
          return [{ lock_acquired: true, id: "run-1" }] as never;
        }
        return [{ lock_acquired: false, id: null }] as never;
      }
      return [] as never;
    });
    sendMock.mockResolvedValue({ id: "evt-1" } as never);

    const [res1, res2] = await Promise.all([POST(), POST()]);
    const statuses = [res1.status, res2.status].sort((a, b) => a - b);

    expect(statuses).toEqual([200, 429]);
    expect(sendMock).toHaveBeenCalledTimes(5);
  });
});
