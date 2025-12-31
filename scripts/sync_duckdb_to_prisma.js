/**
 * Sync DuckDB data to Prisma Postgres
 * Protects our hard-won historical data by pushing to cloud
 */

import 'dotenv/config';
import { PrismaClient } from '../prisma/generated/prisma/client.js';
import { PrismaPg } from '@prisma/adapter-pg';
import duckdb from 'duckdb';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL });
const prisma = new PrismaClient({ adapter });
const DB_PATH = path.join(__dirname, '..', 'data', 'fusion.db');

// Batch size for inserts
const BATCH_SIZE = 1000;

async function syncWeatherObservations() {
  console.log('\n=== SYNCING WEATHER OBSERVATIONS ===');

  const db = new duckdb.Database(DB_PATH, { access_mode: 'READ_ONLY' });
  const conn = db.connect();

  // Get count from DuckDB
  const countResult = await new Promise((resolve, reject) => {
    conn.all('SELECT COUNT(*) as cnt FROM raw.weather_observations_1d', (err, rows) => {
      if (err) reject(err);
      else resolve(rows[0].cnt);
    });
  });
  console.log(`DuckDB has ${countResult.toLocaleString()} weather rows`);

  // Get existing count from Prisma
  const prismaCount = await prisma.rawWeatherObservations.count();
  console.log(`Prisma has ${prismaCount.toLocaleString()} weather rows`);

  if (prismaCount >= countResult) {
    console.log('Prisma already has all weather data, skipping...');
    conn.close();
    db.close();
    return;
  }

  // Get data from DuckDB
  const rows = await new Promise((resolve, reject) => {
    conn.all(`
      SELECT
        station_id,
        obs_date as as_of_date,
        tmax_c as temp_max,
        tmin_c as temp_min,
        prcp_mm as precip,
        NULL as humidity
      FROM raw.weather_observations_1d
      ORDER BY obs_date, station_id
    `, (err, rows) => {
      if (err) reject(err);
      else resolve(rows);
    });
  });

  console.log(`Fetched ${rows.length.toLocaleString()} rows from DuckDB`);

  // Upsert in batches
  let inserted = 0;
  for (let i = 0; i < rows.length; i += BATCH_SIZE) {
    const batch = rows.slice(i, i + BATCH_SIZE);

    try {
      await prisma.$transaction(
        batch.map(row =>
          prisma.rawWeatherObservations.upsert({
            where: {
              stationId_asOfDate: {
                stationId: row.station_id,
                asOfDate: new Date(row.as_of_date)
              }
            },
            update: {
              tempMax: row.temp_max,
              tempMin: row.temp_min,
              precip: row.precip,
              humidity: row.humidity
            },
            create: {
              stationId: row.station_id,
              asOfDate: new Date(row.as_of_date),
              tempMax: row.temp_max,
              tempMin: row.temp_min,
              precip: row.precip,
              humidity: row.humidity
            }
          })
        )
      );
      inserted += batch.length;
      if (inserted % 10000 === 0) {
        console.log(`  Progress: ${inserted.toLocaleString()} / ${rows.length.toLocaleString()}`);
      }
    } catch (err) {
      console.error(`Error at batch ${i}: ${err.message}`);
    }
  }

  console.log(`Synced ${inserted.toLocaleString()} weather observations to Prisma`);
  conn.close();
  db.close();
}

async function syncCftcCot() {
  console.log('\n=== SYNCING CFTC COT ===');

  const db = new duckdb.Database(DB_PATH, { access_mode: 'READ_ONLY' });
  const conn = db.connect();

  // Get from archive.cftc_cot_1w
  const rows = await new Promise((resolve, reject) => {
    conn.all(`
      SELECT
        symbol as contract_code,
        report_date as as_of_date,
        prod_merc_long as commercial_long,
        prod_merc_short as commercial_short,
        managed_money_long as non_commercial_long,
        managed_money_short as non_commercial_short,
        open_interest
      FROM archive.cftc_cot_1w
      ORDER BY report_date, symbol
    `, (err, rows) => {
      if (err) reject(err);
      else resolve(rows);
    });
  });

  console.log(`Fetched ${rows.length.toLocaleString()} CFTC rows from DuckDB`);

  // Get existing count from Prisma
  const prismaCount = await prisma.rawCftcCot.count();
  console.log(`Prisma has ${prismaCount.toLocaleString()} CFTC rows`);

  // Upsert in batches
  let inserted = 0;
  for (let i = 0; i < rows.length; i += BATCH_SIZE) {
    const batch = rows.slice(i, i + BATCH_SIZE);

    try {
      await prisma.$transaction(
        batch.map(row =>
          prisma.rawCftcCot.upsert({
            where: {
              contractCode_asOfDate: {
                contractCode: row.contract_code,
                asOfDate: new Date(row.as_of_date)
              }
            },
            update: {
              commercialLong: row.commercial_long,
              commercialShort: row.commercial_short,
              nonCommercialLong: row.non_commercial_long,
              nonCommercialShort: row.non_commercial_short,
              openInterest: row.open_interest
            },
            create: {
              contractCode: row.contract_code,
              asOfDate: new Date(row.as_of_date),
              commercialLong: row.commercial_long,
              commercialShort: row.commercial_short,
              nonCommercialLong: row.non_commercial_long,
              nonCommercialShort: row.non_commercial_short,
              openInterest: row.open_interest
            }
          })
        )
      );
      inserted += batch.length;
    } catch (err) {
      console.error(`Error at batch ${i}: ${err.message}`);
    }
  }

  console.log(`Synced ${inserted.toLocaleString()} CFTC rows to Prisma`);
  conn.close();
  db.close();
}

async function verifySync() {
  console.log('\n=== VERIFICATION ===');

  const tables = [
    { name: 'raw_weather_observations', model: 'rawWeatherObservations' },
    { name: 'raw_cftc_cot', model: 'rawCftcCot' },
    { name: 'raw_market_futures', model: 'rawMarketFutures' },
    { name: 'raw_fred_observations', model: 'rawFredObservations' },
    { name: 'raw_fx_spot', model: 'rawFxSpot' },
    { name: 'raw_epa_rin_prices', model: 'rawEpaRinPrices' },
  ];

  for (const t of tables) {
    try {
      const count = await prisma[t.model].count();
      console.log(`${t.name}: ${count.toLocaleString()} rows`);
    } catch (err) {
      console.log(`${t.name}: ERROR - ${err.message}`);
    }
  }
}

async function main() {
  console.log('=== DUCKDB TO PRISMA SYNC ===');
  console.log(`Database: ${DB_PATH}`);
  console.log(`Time: ${new Date().toISOString()}`);

  try {
    await syncCftcCot();
    await syncWeatherObservations();
    await verifySync();
  } catch (err) {
    console.error('Sync failed:', err);
  } finally {
    await prisma.$disconnect();
  }
}

main();
