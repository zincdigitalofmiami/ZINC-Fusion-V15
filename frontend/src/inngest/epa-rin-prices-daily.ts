import { inngest } from "./client";
import { createHash } from "crypto";
import { Pool, type PoolClient } from "pg";

const EPA_RIN_PAGE_URL =
  "https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information";

const EPA_QLIK_APP_ID = "73b2b6a5-70c6-4820-b3fa-186ac094f10d";
const EPA_QLIK_WS_URL = `wss://edap.epa.gov/public/app/${EPA_QLIK_APP_ID}`;

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

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

async function createIngestRun(client: PoolClient, jobName: string): Promise<string> {
  const result = await client.query(
    `INSERT INTO ops.ingest_run (job_name, status, started_at) VALUES ($1, 'running', NOW()) RETURNING id`,
    [jobName]
  );
  return result.rows[0].id;
}

async function updateIngestRun(
  client: PoolClient,
  runId: string,
  status: string,
  attempted: number,
  inserted: number,
  skipped: number,
  quarantined: number,
  errorMessage?: string
): Promise<void> {
  await client.query(
    `UPDATE ops.ingest_run SET status=$2, completed_at=NOW(),
     rows_attempted=$3, rows_inserted=$4, rows_skipped=$5, rows_quarantined=$6, error_message=$7 WHERE id=$1`,
    [runId, status, attempted, inserted, skipped, quarantined, errorMessage]
  );
}

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

  async connect(url: string): Promise<void> {
    if (typeof WebSocket !== "function") {
      throw new Error("Global WebSocket is not available in this runtime (need Node >= 20).");
    }

    this.ws = new WebSocket(url);

    await new Promise<void>((resolve, reject) => {
      const onOpen = () => {
        cleanup();
        resolve();
      };
      const onError = () => {
        cleanup();
        reject(new Error("EPA Qlik WebSocket connection failed"));
      };
      const onClose = () => {
        cleanup();
        reject(new Error("EPA Qlik WebSocket closed before opening"));
      };
      const cleanup = () => {
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

async function fetchRinPricesFromQlik(): Promise<{ lastReloadTime: string; points: RinPricePoint[] }> {
  const rpc = new QlikRpcClient();
  try {
    await rpc.connect(EPA_QLIK_WS_URL);
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
  } finally {
    rpc.close();
  }
}

export const epaRinPricesDaily = inngest.createFunction(
  { id: "epa-rin-prices-daily", name: "EPA RIN Prices (Qlik) Bronze Ingestion", retries: 3 },
  { cron: "30 14 * * 1-5" },
  async ({ step, logger }) => {
    const client = await pool.connect();
    let runId: string | null = null;
    let rowsAttempted = 0;
    let rowsInserted = 0;
    let rowsSkipped = 0;
    let rowsQuarantined = 0;

    try {
      await step.run("assert-tables", async () => {
        await client.query("SELECT 1 FROM ops.ingest_run LIMIT 1");
        await client.query("SELECT 1 FROM supply.epa_rin_1d LIMIT 1");
      });

      runId = await step.run("create-ingest-run", () =>
        createIngestRun(client, "epa-rin-prices-daily")
      );

      const dbMaxSourceDate = await step.run("db-max-event-date-source", async () => {
        const r = await client.query(
          "SELECT MAX(event_date)::date AS max_date FROM supply.epa_rin_1d WHERE source = 'epa_qlik_public'"
        );
        return r.rows?.[0]?.max_date ?? null;
      });

      const dbMaxOverallDate = await step.run("db-max-event-date-overall", async () => {
        const r = await client.query(
          "SELECT MAX(event_date)::date AS max_date FROM supply.epa_rin_1d"
        );
        return r.rows?.[0]?.max_date ?? null;
      });

      const { lastReloadTime, points } = await step.run("fetch-epa-qlik", async () => {
        return await fetchRinPricesFromQlik();
      });

      const qlikMaxIso =
        points.length > 0
          ? points.reduce((mx, p) => (p.isoDate > mx ? p.isoDate : mx), points[0].isoDate)
          : null;

      logger.info(
        `EPA Qlik last reload: ${lastReloadTime}, qlik_max=${qlikMaxIso ?? "n/a"}, db_max_source=${dbMaxSourceDate ?? "n/a"}, db_max_overall=${dbMaxOverallDate ?? "n/a"}`
      );

      if (dbMaxSourceDate && qlikMaxIso && qlikMaxIso <= String(dbMaxSourceDate)) {
        await step.run("complete-noop", () =>
          updateIngestRun(client, runId!, "success", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined)
        );
        return {
          status: "no_new_data",
          runId,
          qlikLastReloadTime: lastReloadTime,
          qlikMaxIsoDate: qlikMaxIso,
          dbMaxDate: String(dbMaxSourceDate),
          attempted: rowsAttempted,
          inserted: rowsInserted,
          skipped: rowsSkipped,
          quarantined: rowsQuarantined,
        };
      }

      const existingKeys = await step.run("load-existing-keys", async () => {
        const r = await client.query(
          `SELECT rin_type, event_date::date
           FROM supply.epa_rin_1d
           WHERE source = 'epa_qlik_public'`
        );
        return r.rows.map((row) => `${row.rin_type}|${row.event_date}`);
      });

      const existing = new Set(existingKeys);

      const rowsToInsert: Array<
        [
          string,
          string,
          number,
          string,
          string,
          string,
          string,
          string,
          string[],
          string,
        ]
      > = [];

      for (const p of points) {
        if (dbMaxSourceDate && p.isoDate <= String(dbMaxSourceDate)) {
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

        const rawPayload = {
          source: "epa_qlik_public",
          app_id: EPA_QLIK_APP_ID,
          qlik_last_reload_time: p.qlikLastReloadTime,
          transfer_week_date: p.isoDate,
          rin_type: p.rinType,
          price: p.price,
        };

        rowsToInsert.push([
          p.rinType,
          p.isoDate,
          p.price,
          "epa_qlik_public",
          EPA_RIN_PAGE_URL,
          JSON.stringify(rawPayload),
          runId!,
          rowHash,
          ["biofuel"],
          p.qlikLastReloadTime,
        ]);

        existing.add(key);
      }

      if (rowsToInsert.length > 0) {
        await step.run("insert-batches", async () => {
          const cols =
            "(rin_type, event_date, price, source, source_url, raw_payload, ingestion_batch_id, row_hash, specialist_tags, knowledge_time)";
          const batchSize = 500;
          const perRow = 10;

          for (let i = 0; i < rowsToInsert.length; i += batchSize) {
            const batch = rowsToInsert.slice(i, i + batchSize);
            const values: string[] = [];
            const params: (string | number | string[])[] = [];

            for (let r = 0; r < batch.length; r++) {
              const base = r * perRow;
              values.push(
                `($${base + 1}, $${base + 2}::date, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}::jsonb, $${base + 7}, $${base + 8}, $${base + 9}, $${base + 10}::timestamptz)`
              );
              params.push(...batch[r]);
            }

            await client.query(
              `INSERT INTO supply.epa_rin_1d ${cols} VALUES ${values.join(",")}`,
              params
            );
          }
        });

        rowsInserted += rowsToInsert.length;
      }

      await step.run("complete", () =>
        updateIngestRun(client, runId!, "success", rowsAttempted, rowsInserted, rowsSkipped, rowsQuarantined)
      );

      return {
        status: "success",
        runId,
        qlikLastReloadTime: lastReloadTime,
        attempted: rowsAttempted,
        inserted: rowsInserted,
        skipped: rowsSkipped,
        quarantined: rowsQuarantined,
      };
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      if (runId) {
        await updateIngestRun(
          client,
          runId,
          "failed",
          rowsAttempted,
          rowsInserted,
          rowsSkipped,
          rowsQuarantined,
          msg
        );
      }
      throw error;
    } finally {
      client.release();
    }
  }
);
