const DATABENTO_API_KEY = process.env.DATABENTO_API_KEY;
const DATABENTO_BASE_URL = "https://hist.databento.com/v0/timeseries.get_range";

export type DatabentoOhlcvBar = {
  tsEvent: Date;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
};

function requireApiKey(): string {
  if (!DATABENTO_API_KEY) {
    throw new Error("DATABENTO_API_KEY not set");
  }
  return DATABENTO_API_KEY;
}

function basicAuthHeader(apiKey: string): string {
  const token = Buffer.from(`${apiKey}:`).toString("base64");
  return `Basic ${token}`;
}

export async function fetchDatabentoCsv(params: Record<string, string>): Promise<string> {
  const apiKey = requireApiKey();
  const body = new URLSearchParams(params);

  const res = await fetch(DATABENTO_BASE_URL, {
    method: "POST",
    headers: {
      Authorization: basicAuthHeader(apiKey),
      "Content-Type": "application/x-www-form-urlencoded",
    },
    body: body.toString(),
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Databento API error ${res.status}: ${text}`);
  }

  return await res.text();
}

function parseTimestamp(value: string): Date | null {
  if (!value) return null;
  const trimmed = value.trim();
  if (!trimmed) return null;
  if (/^\d+$/.test(trimmed)) {
    const num = Number(trimmed);
    if (!Number.isFinite(num)) return null;
    // Databento timestamps are in nanoseconds when numeric
    const ms = Math.floor(num / 1_000_000);
    return new Date(ms);
  }
  const dt = new Date(trimmed);
  if (Number.isNaN(dt.getTime())) return null;
  return dt;
}

export function parseDatabentoOhlcvCsv(csv: string): DatabentoOhlcvBar[] {
  const lines = csv
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));

  if (lines.length < 2) return [];

  const header = lines[0].split(",");
  const idx = {
    ts_event: header.indexOf("ts_event"),
    open: header.indexOf("open"),
    high: header.indexOf("high"),
    low: header.indexOf("low"),
    close: header.indexOf("close"),
    volume: header.indexOf("volume"),
  };

  if (idx.ts_event === -1 || idx.open === -1 || idx.high === -1 || idx.low === -1 || idx.close === -1) {
    throw new Error("Databento CSV missing required OHLCV columns");
  }

  const bars: DatabentoOhlcvBar[] = [];
  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");
    if (parts.length < header.length) continue;

    const ts = parseTimestamp(parts[idx.ts_event]);
    if (!ts) continue;

    const open = Number(parts[idx.open]);
    const high = Number(parts[idx.high]);
    const low = Number(parts[idx.low]);
    const close = Number(parts[idx.close]);
    const volume = idx.volume >= 0 ? Number(parts[idx.volume]) || 0 : 0;

    if (!Number.isFinite(open) || !Number.isFinite(high) || !Number.isFinite(low) || !Number.isFinite(close)) {
      continue;
    }

    bars.push({
      tsEvent: ts,
      open,
      high,
      low,
      close,
      volume,
    });
  }

  bars.sort((a, b) => a.tsEvent.getTime() - b.tsEvent.getTime());
  return bars;
}

export type DatabentoStatisticsBar = {
  tsEvent: Date;
  openInterest: number;
};

// Databento sentinel values (INT64_MAX = 9223372036854775807)
const INT64_MAX = 9223372036854775807n;

/**
 * Parse Databento statistics schema CSV for open interest data.
 * Statistics schema contains multiple stat types; this filters for stat_type=9 (open interest).
 * 
 * Open interest value can appear in either:
 * - quantity field (if not sentinel INT64_MAX)
 * - price field (if quantity is sentinel, then price * 1e-9)
 */
export function parseDatabentoStatisticsCsv(csv: string): DatabentoStatisticsBar[] {
  const lines = csv
    .split(/\r?\n/)
    .map((l) => l.trim())
    .filter((l) => l.length > 0 && !l.startsWith("#"));

  if (lines.length < 2) return [];

  const header = lines[0].split(",");
  const idx = {
    ts_event: header.indexOf("ts_event"),
    stat_type: header.indexOf("stat_type"),
    quantity: header.indexOf("quantity"),
    price: header.indexOf("price"),
  };

  if (idx.ts_event === -1) {
    throw new Error("Databento statistics CSV missing required ts_event column");
  }

  if (idx.stat_type === -1) {
    throw new Error("Databento statistics CSV missing required stat_type column");
  }

  const bars: DatabentoStatisticsBar[] = [];
  for (let i = 1; i < lines.length; i++) {
    const parts = lines[i].split(",");
    if (parts.length < header.length) continue;

    const ts = parseTimestamp(parts[idx.ts_event]);
    if (!ts) continue;

    // Filter for open interest (stat_type=9)
    const statType = Number(parts[idx.stat_type]);
    if (!Number.isFinite(statType) || statType !== 9) {
      continue; // Skip non-open-interest stats
    }

    // Extract open interest value: quantity if not sentinel, else price * 1e-9
    let oiValue: number | null = null;

    if (idx.quantity >= 0) {
      const qtyStr = parts[idx.quantity]?.trim();
      if (qtyStr) {
        // Handle large integers that might exceed Number.MAX_SAFE_INTEGER
        const qtyBigInt = BigInt(qtyStr);
        if (qtyBigInt !== INT64_MAX) {
          oiValue = Number(qtyBigInt);
        }
      }
    }

    // If quantity was sentinel or missing, try price field
    if (oiValue === null && idx.price >= 0) {
      const priceStr = parts[idx.price]?.trim();
      if (priceStr) {
        const priceBigInt = BigInt(priceStr);
        if (priceBigInt !== INT64_MAX) {
          // Price is in fixed-point format, scale by 1e-9
          oiValue = Number(priceBigInt) * 1e-9;
        }
      }
    }

    if (oiValue === null || oiValue < 0 || !Number.isFinite(oiValue)) {
      continue;
    }

    bars.push({
      tsEvent: ts,
      openInterest: Math.floor(oiValue), // OI is integer
    });
  }

  bars.sort((a, b) => a.tsEvent.getTime() - b.tsEvent.getTime());
  return bars;
}
