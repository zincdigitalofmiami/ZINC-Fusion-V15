import { inngest } from "./client";
import { Pool } from "pg";

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

// Key FRED series for specialist features
const FRED_SERIES = [
  // FED Domain
  { id: "DFF", name: "Fed Funds Rate" },
  { id: "T10Y2Y", name: "10Y-2Y Treasury Spread" },
  { id: "T10YIE", name: "10Y Breakeven Inflation" },
  { id: "DFII10", name: "10Y Real Rate" },

  // FX Domain
  { id: "DTWEXBGS", name: "Trade Weighted Dollar Index" },
  { id: "DEXCHUS", name: "CNY/USD Exchange Rate" },
  { id: "DEXBZUS", name: "BRL/USD Exchange Rate" },

  // Energy Domain
  { id: "DCOILWTICO", name: "WTI Crude Oil" },
  { id: "DHHNGSP", name: "Henry Hub Natural Gas" },

  // Volatility Domain
  { id: "VIXCLS", name: "CBOE VIX" },
  { id: "BAMLH0A0HYM2", name: "High Yield Spread" },

  // Biofuel Domain
  { id: "GASREGW", name: "Regular Gas Price" },
  { id: "GASDESW", name: "Diesel Price" },

  // China Domain
  { id: "EXCHUS", name: "China Exchange Rate" },
];

interface FredObservation {
  date: string;
  value: string;
}

/**
 * Fetch daily observations from FRED API
 * Runs daily at 10:00 AM ET (after FRED updates)
 */
export const fredDaily = inngest.createFunction(
  { id: "fred-daily", name: "FRED Daily Observations" },
  { cron: "0 15 * * 1-5" }, // 10AM ET = 3PM UTC, Mon-Fri
  async ({ step }) => {
    const apiKey = process.env.FRED_API_KEY;
    if (!apiKey) {
      return { status: "error", message: "FRED_API_KEY not configured" };
    }

    const results: { series: string; status: string; value?: number }[] = [];

    for (const series of FRED_SERIES) {
      await step.run(`fetch-${series.id}`, async () => {
        try {
          // Fetch latest observation
          const res = await fetch(
            `https://api.stlouisfed.org/fred/series/observations?series_id=${series.id}&api_key=${apiKey}&file_type=json&sort_order=desc&limit=1`
          );
          const json = await res.json();
          const obs = json.observations?.[0] as FredObservation | undefined;

          if (!obs || obs.value === ".") {
            results.push({ series: series.id, status: "no_data" });
            return;
          }

          const value = parseFloat(obs.value);
          if (isNaN(value)) {
            results.push({ series: series.id, status: "invalid_value" });
            return;
          }

          // Insert into database
          const client = await pool.connect();
          try {
            await client.query(
              `INSERT INTO raw.fred_observations_1d
                (as_of_date, series_id, value, source, ingested_at)
               VALUES ($1::date, $2, $3, 'fred_api', NOW())
               ON CONFLICT (as_of_date, series_id) DO UPDATE SET
                 value = EXCLUDED.value,
                 source = EXCLUDED.source,
                 ingested_at = EXCLUDED.ingested_at`,
              [obs.date, series.id, value]
            );
            results.push({ series: series.id, status: "success", value });
          } finally {
            client.release();
          }
        } catch (error) {
          results.push({ series: series.id, status: "error" });
        }
      });
    }

    return {
      status: "complete",
      date: new Date().toISOString().split("T")[0],
      results,
      successCount: results.filter((r) => r.status === "success").length,
      errorCount: results.filter((r) => r.status !== "success").length,
    };
  }
);
