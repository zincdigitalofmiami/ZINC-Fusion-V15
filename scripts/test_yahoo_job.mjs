#!/usr/bin/env node
/**
 * Test script to manually verify Yahoo EOD job with the event_date fix
 * This simulates what the Inngest job does, locally.
 */

import "dotenv/config";
import pg from "pg";
const { Pool } = pg;

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: { rejectUnauthorized: false },
});

const YAHOO_SYMBOLS = [
  { yahoo: "ZL=F", db: "ZL", name: "Soybean Oil" },
  { yahoo: "ZS=F", db: "ZS", name: "Soybeans" },
  { yahoo: "ZC=F", db: "ZC", name: "Corn" },
  { yahoo: "CL=F", db: "CL", name: "Crude Oil" },
];

async function testYahooEod() {
  console.log("=== TESTING YAHOO EOD JOB (event_date fix) ===\n");

  // Step 1: Fetch quotes from Yahoo
  const symbols = YAHOO_SYMBOLS.map((s) => s.yahoo).join(",");
  console.log(`Fetching quotes for: ${symbols}`);
  
  const res = await fetch(
    `https://query1.finance.yahoo.com/v7/finance/quote?symbols=${encodeURIComponent(symbols)}`
  );
  const json = await res.json();
  const quotes = json.quoteResponse?.result;

  if (!quotes || quotes.length === 0) {
    console.error("ERROR: No quotes returned from Yahoo");
    process.exit(1);
  }

  console.log(`Got ${quotes.length} quotes\n`);

  // Step 2: Test insert with event_date column
  const client = await pool.connect();
  let inserted = 0;
  let errors = 0;

  try {
    for (const config of YAHOO_SYMBOLS) {
      const quote = quotes.find(
        (q) => q.symbol === config.yahoo || q.symbol === config.yahoo.replace("=F", "")
      );

      if (!quote) {
        console.log(`  ${config.db}: NOT FOUND in Yahoo response`);
        continue;
      }

      try {
        // Using event_date (the FIXED column name)
        await client.query(
          `INSERT INTO raw.market_futures_1d
            (event_date, symbol, open, high, low, close, volume, source, ingested_at)
           VALUES (CURRENT_DATE, $1, $2, $3, $4, $5, $6, 'yahoo_eod_test', NOW())
           ON CONFLICT (event_date, symbol) DO UPDATE SET
             open = EXCLUDED.open,
             high = EXCLUDED.high,
             low = EXCLUDED.low,
             close = EXCLUDED.close,
             volume = EXCLUDED.volume,
             source = EXCLUDED.source,
             ingested_at = EXCLUDED.ingested_at`,
          [
            config.db,
            quote.regularMarketOpen,
            quote.regularMarketHigh,
            quote.regularMarketLow,
            quote.regularMarketPrice,
            quote.regularMarketVolume || 0,
          ]
        );
        console.log(`  ${config.db}: ✅ INSERTED close=${quote.regularMarketPrice}`);
        inserted++;
      } catch (err) {
        console.log(`  ${config.db}: ❌ ERROR - ${err.message}`);
        errors++;
      }
    }

    console.log(`\n=== RESULTS ===`);
    console.log(`Inserted: ${inserted}`);
    console.log(`Errors: ${errors}`);

    // Verify by reading back
    const verify = await client.query(
      `SELECT event_date, symbol, close, source, ingested_at 
       FROM raw.market_futures_1d 
       WHERE event_date = CURRENT_DATE AND source = 'yahoo_eod_test'
       ORDER BY symbol`
    );
    
    console.log(`\n=== VERIFICATION ===`);
    verify.rows.forEach(r => {
      console.log(`  ${r.event_date} | ${r.symbol} | close=${r.close} | ${r.source} | ${r.ingested_at}`);
    });

  } finally {
    client.release();
    await pool.end();
  }
}

testYahooEod().catch(console.error);
