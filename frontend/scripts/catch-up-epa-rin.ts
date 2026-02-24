#!/usr/bin/env npx tsx
/**
 * catch-up-epa-rin.ts
 *
 * Backfills EPA RIN prices via Qlik WebSocket.
 * Same logic as epa-rin-prices-daily.ts but runs standalone.
 *
 * Usage:
 *   cd frontend
 *   npx tsx scripts/catch-up-epa-rin.ts
 */

import pg from "pg";
import { createHash } from "crypto";
import { readFileSync } from "fs";

// Load .env.local
try {
  const envContent = readFileSync(".env.local", "utf-8");
  for (const line of envContent.split("\n")) {
    const match = line.match(/^([A-Z_]+)="?([^"]*)"?\s*$/);
    if (match && !process.env[match[1]]) {
      process.env[match[1]] = match[2];
    }
  }
} catch { /* ignore */ }

const DATABASE_URL = process.env.DATABASE_URL;
if (!DATABASE_URL) { console.error("DATABASE_URL not set"); process.exit(1); }

const pool = new pg.Pool({ connectionString: DATABASE_URL, ssl: { rejectUnauthorized: false }, max: 2 });

const EPA_QLIK_APP_ID = "73b2b6a5-70c6-4820-b3fa-186ac094f10d";
const EPA_QLIK_WS_URL = `wss://edap.epa.gov/public/app/${EPA_QLIK_APP_ID}`;

function computeRowHash(parts: string[]): string {
  return createHash("sha256").update(parts.join("|")).digest("hex");
}

function parseUsDateToIso(dateText: string): string {
  const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(dateText.trim());
  if (!match) throw new Error(`Bad date: ${dateText}`);
  return `${match[3]}-${match[1].padStart(2, "0")}-${match[2].padStart(2, "0")}`;
}

function parseNumber(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value !== "string") return null;
  const num = Number(value.trim());
  return Number.isFinite(num) ? num : null;
}

type PendingRpc = { resolve: (v: unknown) => void; reject: (e: Error) => void; timeout: ReturnType<typeof setTimeout> };

class QlikRpcClient {
  private ws: WebSocket | null = null;
  private nextId = 1;
  private pending = new Map<number, PendingRpc>();

  async connect(url: string, timeoutMs = 45000): Promise<void> {
    this.ws = new WebSocket(url);
    await new Promise<void>((resolve, reject) => {
      const t = setTimeout(() => { cleanup(); reject(new Error("WS timeout")); }, timeoutMs);
      const onOpen = () => { cleanup(); resolve(); };
      const onError = (e: Event) => { cleanup(); reject(new Error(`WS error: ${(e as ErrorEvent)?.message}`)); };
      const onClose = (e: CloseEvent) => { cleanup(); reject(new Error(`WS closed: ${e?.code}`)); };
      const cleanup = () => { clearTimeout(t); this.ws?.removeEventListener("open", onOpen); this.ws?.removeEventListener("error", onError); this.ws?.removeEventListener("close", onClose); };
      this.ws?.addEventListener("open", onOpen);
      this.ws?.addEventListener("error", onError);
      this.ws?.addEventListener("close", onClose);
    });
    this.ws.addEventListener("message", (event: MessageEvent) => {
      try {
        const msg = JSON.parse(typeof event?.data === "string" ? event.data : String(event?.data));
        if (!msg?.id || !this.pending.has(msg.id)) return;
        const p = this.pending.get(msg.id)!;
        this.pending.delete(msg.id);
        clearTimeout(p.timeout);
        if (msg?.error) { p.reject(new Error(msg.error.message || "RPC error")); return; }
        p.resolve(msg.result);
      } catch { /* ignore */ }
    });
  }

  async call<T>(handle: number, method: string, params: unknown[], timeoutMs = 30000): Promise<T> {
    if (!this.ws) throw new Error("Not connected");
    const id = this.nextId++;
    this.ws.send(JSON.stringify({ jsonrpc: "2.0", id, handle, method, params }));
    return new Promise<T>((resolve, reject) => {
      const timeout = setTimeout(() => { this.pending.delete(id); reject(new Error(`RPC timeout: ${method}`)); }, timeoutMs);
      this.pending.set(id, { resolve: (v) => resolve(v as T), reject, timeout });
    });
  }

  close(): void {
    if (!this.ws) return;
    try { this.ws.close(); } finally {
      this.ws = null;
      for (const [, p] of this.pending) { clearTimeout(p.timeout); p.reject(new Error("Cancelled")); }
      this.pending.clear();
    }
  }
}

type RinPoint = { isoDate: string; rinType: string; price: number; qlikReload: string };

async function fetchRinPrices(maxRetries = 3): Promise<{ reload: string; points: RinPoint[] }> {
  let lastError: Error | null = null;

  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    const rpc = new QlikRpcClient();
    try {
      console.log(`  Attempt ${attempt}/${maxRetries}: connecting to EPA Qlik WebSocket...`);
      await rpc.connect(EPA_QLIK_WS_URL, 45000);
      console.log("  Connected. Opening doc...");

      const openRes = await rpc.call<{ qReturn?: { qHandle?: number } }>(-1, "OpenDoc", [EPA_QLIK_APP_ID, "", "", "", false]);
      const docHandle = openRes?.qReturn?.qHandle;
      if (!docHandle) throw new Error("No doc handle");

      const layoutRes = await rpc.call<{ qLayout?: { qLastReloadTime?: string } }>(docHandle, "GetAppLayout", []);
      const reload = layoutRes?.qLayout?.qLastReloadTime ?? "unknown";
      console.log(`  Qlik last reload: ${reload}`);

      const cubeDef = {
        qInfo: { qType: "epa_rin_catchup" },
        qHyperCubeDef: {
          qDimensions: [
            { qDef: { qFieldDefs: ["=[Price_Transfer Date by week.autoCalendar.Date]"], qFieldLabels: ["Transfer Date"] } },
            { qDef: { qFieldDefs: ["=Price_FUEL_CD_TXT"], qFieldLabels: ["Fuel Code"] } },
          ],
          qMeasures: [{
            qDef: {
              qLabel: "RIN Price",
              qDef: 'Sum({$<[Price_FUEL_CD]={"3","4","5","6"}>}Price_INTERMEDIATE_PRICE)/Sum({$<[Price_FUEL_CD]={"3","4","5","6"}>}Price_TOTAL_RINS)',
            },
          }],
        },
      };

      const sessRes = await rpc.call<{ qReturn?: { qHandle?: number } }>(docHandle, "CreateSessionObject", [cubeDef]);
      const cubeHandle = sessRes?.qReturn?.qHandle;
      if (!cubeHandle) throw new Error("No cube handle");

      const sizeRes = await rpc.call<{ qLayout?: { qHyperCube?: { qSize?: { qcy?: number } } } }>(cubeHandle, "GetLayout", []);
      const totalRows = sizeRes?.qLayout?.qHyperCube?.qSize?.qcy ?? 0;
      console.log(`  Cube has ${totalRows} rows`);

      const dataRes = await rpc.call<{ qDataPages?: Array<{ qMatrix?: Array<Array<{ qText?: string; qNum?: number }>> }> }>(
        cubeHandle, "GetHyperCubeData", ["/qHyperCubeDef", [{ qTop: 0, qLeft: 0, qHeight: totalRows, qWidth: 3 }]]
      );

      const matrix = dataRes?.qDataPages?.[0]?.qMatrix;
      if (!Array.isArray(matrix)) throw new Error("No matrix");

      const points: RinPoint[] = [];
      for (const row of matrix) {
        const dateText = row?.[0]?.qText;
        const rinType = row?.[1]?.qText;
        const priceRaw = row?.[2]?.qText ?? row?.[2]?.qNum;
        if (typeof dateText !== "string" || typeof rinType !== "string") continue;
        if (!["D3", "D4", "D5", "D6"].includes(rinType)) continue;
        const price = parseNumber(priceRaw);
        if (price === null) continue;
        points.push({ isoDate: parseUsDateToIso(dateText), rinType, price, qlikReload: reload });
      }

      rpc.close();
      return { reload, points };
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err));
      rpc.close();
      console.warn(`  Attempt ${attempt} failed: ${lastError.message}`);
      if (attempt < maxRetries) {
        const backoff = 5000 * Math.pow(3, attempt - 1);
        console.log(`  Retrying in ${backoff / 1000}s...`);
        await new Promise((r) => setTimeout(r, backoff));
      }
    }
  }
  throw lastError || new Error("All retries failed");
}

async function main() {
  console.log("═══ EPA RIN Catch-Up ═══");

  const client = await pool.connect();
  try {
    const maxRes = await client.query("SELECT MAX(event_date)::text as latest FROM supply.epa_rin_1d WHERE source = 'epa_qlik_public'");
    const dbMax = maxRes.rows[0]?.latest ?? "2000-01-01";
    console.log(`DB latest: ${dbMax}`);

    const existingRes = await client.query("SELECT rin_type || '|' || event_date::text as key FROM supply.epa_rin_1d WHERE source = 'epa_qlik_public'");
    const existing = new Set(existingRes.rows.map((r: { key: string }) => r.key));
    console.log(`Existing keys: ${existing.size}`);

    const { reload, points } = await fetchRinPrices();
    console.log(`Fetched ${points.length} RIN price points from Qlik`);

    const qlikMax = points.length > 0 ? points.reduce((mx, p) => (p.isoDate > mx ? p.isoDate : mx), points[0].isoDate) : null;
    console.log(`Qlik max date: ${qlikMax}`);

    if (qlikMax && qlikMax <= dbMax) {
      console.log("No new data available.");
      await pool.end();
      return;
    }

    // Filter to new rows only
    const newPoints = points.filter((p) => {
      if (p.isoDate <= dbMax) return false;
      const key = `${p.rinType}|${p.isoDate}`;
      if (existing.has(key)) return false;
      existing.add(key);
      return true;
    });

    console.log(`New points to insert: ${newPoints.length}`);

    if (newPoints.length > 0) {
      // Batch insert
      const batchSize = 500;
      for (let i = 0; i < newPoints.length; i += batchSize) {
        const batch = newPoints.slice(i, i + batchSize);
        const values: string[] = [];
        const params: (string | number)[] = [];

        for (let r = 0; r < batch.length; r++) {
          const p = batch[r];
          const base = r * 6;
          const rowHash = computeRowHash(["epa_qlik_public", "https://www.epa.gov/fuels-registration-reporting-and-compliance-help/rin-trades-and-price-information", p.rinType, p.isoDate, String(p.price), p.qlikReload]);
          values.push(`($${base + 1}, $${base + 2}::date, $${base + 3}, $${base + 4}, $${base + 5}, $${base + 6}::timestamptz)`);
          params.push(p.rinType, p.isoDate, p.price, "epa_qlik_public", rowHash, reload);
        }

        await client.query(
          `INSERT INTO supply.epa_rin_1d (rin_type, event_date, price, source, row_hash, knowledge_time) VALUES ${values.join(",")}`,
          params
        );
      }

      console.log(`Inserted ${newPoints.length} rows`);
    }

    // Verify
    const verifyRes = await client.query("SELECT MAX(event_date)::text as latest, COUNT(*) as total FROM supply.epa_rin_1d");
    console.log(`EPA RIN now: ${verifyRes.rows[0]?.total} rows, latest=${verifyRes.rows[0]?.latest}`);
  } finally {
    client.release();
  }

  await pool.end();
}

main().catch((err) => { console.error("Fatal:", err); process.exit(1); });
