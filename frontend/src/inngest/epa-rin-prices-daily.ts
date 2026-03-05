/**
 * EPA RIN Prices (Qlik) Data Ingestion
 *
 * INGESTION CONTRACT:
 * - Logs each run in ops.ingest_run
 * - Computes row_hash for idempotency
 * - Append-only inserts (no upserts)
 *
 * SOURCE: EPA Qlik Public App via WebSocket RPC
 * - Fetches D3, D4, D5, D6 RIN price points
 * - No API key required (public WebSocket)
 *
 * @author Claude (ZINC-FUSION-V15)
 * @version 1.1.0
 * @date 2026-02-16
 */

import { inngest, DB_CONCURRENCY } from "./client";
import { createHash } from "crypto";
import { getIngestPool } from "@/lib/db";

const EPA_RIN_PAGE_URL =
  "https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information";

const EPA_QLIK_APP_ID = "73b2b6a5-70c6-4820-b3fa-186ac094f10d";
const EPA_QLIK_WS_URL = `wss://edap.epa.gov/public/app/${EPA_QLIK_APP_ID}`;

const pool = getIngestPool();

function computeRowHash(parts: string[]): string {
  return createHash("sha256").update(parts.join("|")).digest("hex");
}

function parseUsDateToIso(dateText: string): string {
  const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(dateText.trim());
  if (!match) {
    throw new Error(`Unexpected date format from EPA Qlik: ${JSON.stringify(dateText)}`);
  }
  const month = match[1].padStart(2, "0");
  const day = match[2].padStart(2, "0");
  const year = match[3];
  return `${year}-${month}-${day}`;
}

function parseNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  const num = Number(trimmed);
  return Number.isFinite(num) ? num : null;
}

// PoolClient helper functions removed — SQL inlined inside step.run() closures
// to prevent stale connections across Inngest durable execution boundaries.

type PendingRpc = {
  resolve: (value: unknown) => void;
  reject: (err: Error) => void;
  timeout: ReturnType<typeof setTimeout>;
};

interface QlikRpcResponse {
  id?: number;
  result?: unknown;
  error?: { message?: string };
}

interface QlikOpenDocResult {
  qReturn?: { qHandle?: number };
}

interface QlikAppLayoutResult {
  qLayout?: { qLastReloadTime?: string };
}

interface QlikSessionObjectResult {
  qReturn?: { qHandle?: number };
}

interface QlikLayoutResult {
  qLayout?: { qHyperCube?: { qSize?: { qcy?: number } } };
}

interface QlikHyperCubeCell {
  qText?: string;
  qNum?: number;
}

interface QlikDataPagesResult {
  qDataPages?: Array<{ qMatrix?: QlikHyperCubeCell[][] }>;
}

class QlikRpcClient {
  private ws: WebSocket | null = null;
  private nextId = 1;
  private pending = new Map<number, PendingRpc>();

  async connect(url: string, timeoutMs: number = 30_000): Promise<void> {
    if (typeof WebSocket !== "function") {
      throw new Error("Global WebSocket is not available in this runtime (need Node >= 20).");
    }

    this.ws = new WebSocket(url);

    await new Promise<void>((resolve, reject) => {
      const connectionTimeout = setTimeout(() => {
        cleanup();
        reject(new Error(`EPA Qlik WebSocket connection timeout after ${timeoutMs}ms`));
      }, timeoutMs);

      const onOpen = () => {
        cleanup();
        resolve();
      };
      const onError = (event: Event) => {
        cleanup();
        const errorDetail = (event as ErrorEvent)?.message || "unknown error";
        reject(new Error(`EPA Qlik WebSocket connection failed: ${errorDetail}`));
      };
      const onClose = (event: CloseEvent) => {
        cleanup();
        reject(new Error(`EPA Qlik WebSocket closed before opening: code=${event?.code}, reason=${event?.reason || "none"}`));
      };
      const cleanup = () => {
        clearTimeout(connectionTimeout);
        this.ws?.removeEventListener("open", onOpen);
        this.ws?.removeEventListener("error", onError);
        this.ws?.removeEventListener("close", onClose);
      };

      this.ws?.addEventListener("open", onOpen);
      this.ws?.addEventListener("error", onError);
      this.ws?.addEventListener("close", onClose);
    });

    this.ws.addEventListener("message", (event: MessageEvent) => {
      try {
        const data = typeof event?.data === "string" ? event.data : String(event?.data);
        const msg: QlikRpcResponse = JSON.parse(data);
        const id = msg?.id;
        if (!id || !this.pending.has(id)) return;
        const pending = this.pending.get(id)!;
        this.pending.delete(id);
        clearTimeout(pending.timeout);
        if (msg?.error) {
          pending.reject(new Error(msg.error.message || "EPA Qlik RPC error"));
          return;
        }
        pending.resolve(msg.result);
      } catch {
        return;
      }
    });
  }

  async call<T>(handle: number, method: string, params: unknown[], timeoutMs = 30_000): Promise<T> {
    if (!this.ws) throw new Error("EPA Qlik WebSocket is not connected");
    const id = this.nextId++;
    const payload = { jsonrpc: "2.0", id, handle, method, params };

    return await new Promise<T>((resolve, reject) => {
      const timeout = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`EPA Qlik RPC timeout: ${method}`));
      }, timeoutMs);

      this.pending.set(id, { resolve: (value) => resolve(value as T), reject, timeout });
      this.ws!.send(JSON.stringify(payload));
    });
  }

  close(): void {
    if (!this.ws) return;
    try {
      this.ws.close();
    } finally {
      this.ws = null;
      for (const [id, pending] of this.pending.entries()) {
        clearTimeout(pending.timeout);
        pending.reject(new Error(`EPA Qlik RPC canceled: ${id}`));
      }
      this.pending.clear();
    }
  }
}

type RinPricePoint = {
  isoDate: string;
  rinType: string;
  price: number;
  qlikLastReloadTime: string;
};

async function fetchRinPricesFromQlik(maxRetries: number = 3): Promise<{ lastReloadTime: string; points: RinPricePoint[] }> {
  let lastError: Error | null = null;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    const rpc = new QlikRpcClient();
    try {
      await rpc.connect(EPA_QLIK_WS_URL, 45_000); // 45s timeout for connection
    const openRes = await rpc.call<QlikOpenDocResult>(-1, "OpenDoc", [EPA_QLIK_APP_ID, "", "", "", false]);
    const docHandle: number | undefined = openRes?.qReturn?.qHandle;
    if (!docHandle) throw new Error("EPA Qlik OpenDoc returned no doc handle");

    const appLayoutRes = await rpc.call<QlikAppLayoutResult>(docHandle, "GetAppLayout", []);
    const lastReloadTime: string | undefined = appLayoutRes?.qLayout?.qLastReloadTime;
    if (!lastReloadTime) throw new Error("EPA Qlik did not provide qLastReloadTime");

    const cubeDef = {
      qInfo: { qType: "epa_rin_prices_extract" },
      qHyperCubeDef: {
        qDimensions: [
          {
            qDef: {
              qFieldDefs: ["=[Price_Transfer Date by week.autoCalendar.Date]"],
              qFieldLabels: ["Transfer Date by Week"],
            },
          },
          {
            qDef: {
              qFieldDefs: ["=Price_FUEL_CD_TXT"],
              qFieldLabels: ["Fuel (D Code)"],
            },
          },
        ],
        qMeasures: [
          {
            qDef: {
              qLabel: "RIN Price",
              qDef: 'Sum({$<[Price_FUEL_CD]={"3","4","5","6"}>}Price_INTERMEDIATE_PRICE)/Sum({$<[Price_FUEL_CD]={"3","4","5","6"}>}Price_TOTAL_RINS)',
            },
          },
        ],
      },
    };

    const sessionRes = await rpc.call<QlikSessionObjectResult>(docHandle, "CreateSessionObject", [cubeDef]);
    const cubeHandle: number | undefined = sessionRes?.qReturn?.qHandle;
    if (!cubeHandle) throw new Error("EPA Qlik CreateSessionObject returned no handle");

    const layoutRes = await rpc.call<QlikLayoutResult>(cubeHandle, "GetLayout", []);
    const qSize = layoutRes?.qLayout?.qHyperCube?.qSize;
    if (!qSize || typeof qSize.qcy !== "number") throw new Error("EPA Qlik cube has no qSize");

    const dataRes = await rpc.call<QlikDataPagesResult>(cubeHandle, "GetHyperCubeData", [
      "/qHyperCubeDef",
      [{ qTop: 0, qLeft: 0, qHeight: qSize.qcy, qWidth: 3 }],
    ]);

    const matrix: QlikHyperCubeCell[][] | undefined = dataRes?.qDataPages?.[0]?.qMatrix;
    if (!Array.isArray(matrix)) throw new Error("EPA Qlik cube returned no data matrix");

    const points: RinPricePoint[] = [];
    for (const row of matrix) {
      const dateText = row?.[0]?.qText;
      const rinType = row?.[1]?.qText;
      const priceRaw = row?.[2]?.qText ?? row?.[2]?.qNum;

      if (typeof dateText !== "string" || typeof rinType !== "string") continue;
      if (!["D3", "D4", "D5", "D6"].includes(rinType)) continue;
      const price = parseNumber(priceRaw);
      if (price === null) continue;

      points.push({
        isoDate: parseUsDateToIso(dateText),
        rinType,
        price,
        qlikLastReloadTime: lastReloadTime,
      });
    }

      return { lastReloadTime, points };
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      rpc.close();

      if (attempt < maxRetries) {
        // Exponential backoff: 5s, 15s, 45s
        const backoffMs = 5000 * Math.pow(3, attempt - 1);
        await new Promise((r) => setTimeout(r, backoffMs));
      }
    }
  }

  throw lastError || new Error("EPA Qlik fetch failed after all retries");
}

export const epaRinPricesDaily = inngest.createFunction(
  { id: "epa-rin-prices-daily", name: "EPA RIN Prices (Qlik) Data Ingestion", retries: 3, concurrency: [DB_CONCURRENCY] },
  { cron: "30 16 * * *" }, // Daily at 16:30 UTC
  async ({ step, logger }) => {
    // ── Step 1: assert tables exist ──
    await step.run("assert-tables", async () => {
      const client = await pool.connect();
      try {
        await client.query("SELECT 1 FROM ops.ingest_run LIMIT 1");
        await client.query("SELECT 1 FROM supply.epa_rin_1d LIMIT 1");
      } finally {
        client.release();
      }
    });

    // ── Step 2: create ingest run ──
    const runId = await step.run("create-ingest-run", async () => {
      const client = await pool.connect();
      try {
        const result = await client.query(
          `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
          ["epa-rin-prices-daily"]
        );
        return result.rows[0].id as string;
      } finally {
        client.release();
      }
    });

    // ── Step 3: load DB state (max dates + existing keys in one step) ──
    const dbState = await step.run("load-db-state", async () => {
      const client = await pool.connect();
      try {
        const maxSourceRes = await client.query(
          "SELECT MAX(event_date)::date AS max_date FROM supply.epa_rin_1d WHERE source = 'epa_qlik_public'"
        );
        const dbMaxSourceDate: string | null = maxSourceRes.rows?.[0]?.max_date ?? null;

        const maxOverallRes = await client.query(
          "SELECT MAX(event_date)::date AS max_date FROM supply.epa_rin_1d"
        );
        const dbMaxOverallDate: string | null = maxOverallRes.rows?.[0]?.max_date ?? null;

        const existingRes = await client.query(
          `SELECT rin_type, event_date::date
           FROM supply.epa_rin_1d
           WHERE source = 'epa_qlik_public'`
        );
        const existingKeys = existingRes.rows.map((row: { rin_type: string; event_date: string }) => `${row.rin_type}|${row.event_date}`);

        return { dbMaxSourceDate, dbMaxOverallDate, existingKeys };
      } finally {
        client.release();
      }
    });

    // ── Step 4: fetch from EPA Qlik WebSocket ──
    const { lastReloadTime, points } = await step.run("fetch-epa-qlik", async () => {
      return await fetchRinPricesFromQlik();
    });

    const qlikMaxIso =
      points.length > 0
        ? points.reduce((mx, p) => (p.isoDate > mx ? p.isoDate : mx), points[0].isoDate)
        : null;

    logger.info(
      `EPA Qlik last reload: ${lastReloadTime}, qlik_max=${qlikMaxIso ?? "n/a"}, db_max_source=${dbState.dbMaxSourceDate ?? "n/a"}, db_max_overall=${dbState.dbMaxOverallDate ?? "n/a"}`
    );

    // Short-circuit if no new data
    if (dbState.dbMaxSourceDate && qlikMaxIso && qlikMaxIso <= String(dbState.dbMaxSourceDate)) {
      await step.run("complete-noop", async () => {
        const client = await pool.connect();
        try {
          await client.query(
            `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
             rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
            [runId, "success", 0, 0, 0, 0]
          );
        } finally {
          client.release();
        }
      });
      return {
        status: "no_new_data",
        runId,
        qlikLastReloadTime: lastReloadTime,
        qlikMaxIsoDate: qlikMaxIso,
        dbMaxDate: String(dbState.dbMaxSourceDate),
        attempted: 0,
        inserted: 0,
        skipped: 0,
        quarantined: 0,
      };
    }

    // ── Compute rows to insert (pure computation, no DB needed) ──
    const existing = new Set(dbState.existingKeys);
    let rowsAttempted = 0;
    let rowsSkipped = 0;

    const rowsToInsert: Array<[string, string, number, string, string, string]> = [];

    for (const p of points) {
      if (dbState.dbMaxSourceDate && p.isoDate <= String(dbState.dbMaxSourceDate)) {
        rowsSkipped++;
        continue;
      }

      rowsAttempted++;
      const key = `${p.rinType}|${p.isoDate}`;
      if (existing.has(key)) {
        rowsSkipped++;
        continue;
      }

      const rowHash = computeRowHash([
        "epa_qlik_public",
        EPA_RIN_PAGE_URL,
        p.rinType,
        p.isoDate,
        String(p.price),
        p.qlikLastReloadTime,
      ]);

      rowsToInsert.push([
        p.rinType,
        p.isoDate,
        p.price,
        "epa_qlik_public",
        rowHash,
        p.qlikLastReloadTime,
      ]);

      existing.add(key);
    }

    // ── Step 5: batch insert new rows ──
    if (rowsToInsert.length > 0) {
      await step.run("insert-batches", async () => {
        const client = await pool.connect();
        try {
          const cols = "(rin_type, event_date, price, source, row_hash, knowledge_time)";
          const batchSize = 500;
          const perRow = 6;

          for (let i = 0; i < rowsToInsert.length; i += batchSize) {
            const batch = rowsToInsert.slice(i, i + batchSize);
            const values: string[] = [];
            const params: (string | number | string[])[] = [];

            for (let r = 0; r < batch.length; r++) {
              const base = r * perRow;
              values.push(
                `($${base + 1}, $${base + 2}::date, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}::timestamptz)`
              );
              params.push(...batch[r]);
            }

            await client.query(
              `INSERT INTO supply.epa_rin_1d ${cols} VALUES ${values.join(",")}`,
              params
            );
          }
        } finally {
          client.release();
        }
      });
    }

    const rowsInserted = rowsToInsert.length;

    // ── Step 6: finalize ingest run ──
    await step.run("complete-ingest-run", async () => {
      const client = await pool.connect();
      try {
        await client.query(
          `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
           rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6 WHERE id=$1`,
          [runId, "success", rowsAttempted, rowsInserted, rowsSkipped, 0]
        );
      } finally {
        client.release();
      }
    });

    logger.info(`Completed: ${rowsInserted} inserted, ${rowsSkipped} skipped`);

    return {
      status: "success",
      runId,
      qlikLastReloadTime: lastReloadTime,
      attempted: rowsAttempted,
      inserted: rowsInserted,
      skipped: rowsSkipped,
      quarantined: 0,
    };
  }
);
