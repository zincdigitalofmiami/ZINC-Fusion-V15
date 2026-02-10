/**
 * MANUALLY POPULATE THE 3 MOST CRITICAL SUPPLY TABLES
 *
 * These are MORE IMPORTANT than news/alt data:
 * 1. Brazil soybean production (CONAB) - #1 producer
 * 2. Argentina crush (CIARA) - #1 soy oil exporter
 * 3. Malaysia palm oil (MPOB) - #1 palm producer
 */

const { Pool } = require('pg');
const { createHash } = require('crypto');
require('dotenv').config({ path: require('path').join(__dirname, '../frontend/.env.local') });

const USDA_API_KEY = process.env.USDA_API_KEY?.trim().replace(/\\n/g, '');

async function fetchUSDAPSD(countryCode, commodityCode) {
  const params = new URLSearchParams({
    api_key: USDA_API_KEY,
    countryCode,
    commodityCode,
  });

  const url = `https://apps.fas.usda.gov/OpenData/api/psd/commodityDataByGeoLoc?${params}`;

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`USDA PSD API error: ${response.status} ${response.statusText}`);
  }

  const data = await response.json();
  return data.filter(d => d.marketYear >= "2020/2021");
}

async function main() {
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
  });

  console.log('\n🚨 POPULATING 3 MOST CRITICAL SUPPLY TABLES\n');
  console.log('='.repeat(70) + '\n');

  let totalInserted = 0;

  // 1. BRAZIL SOYBEAN PRODUCTION (CONAB proxy via USDA)
  console.log('1️⃣  BRAZIL SOYBEAN PRODUCTION (CONAB proxy)\n');
  try {
    const brData = await fetchUSDAPSD('BR', '2222'); // Brazil, Soybeans
    console.log(`   Fetched ${brData.length} Brazil records`);

    let inserted = 0;
    for (const record of brData) {
      const year = record.marketYear.split('/')[0];
      const reportMonth = new Date(`${year}-07-01`);
      const rowHash = createHash('sha256').update(`BR|${record.marketYear}|${record.attributeDescription}`).digest('hex');

      const value = parseFloat(record.value);
      if (isNaN(value)) continue;

      if (record.attributeDescription === 'Production') {
        await pool.query(
          `INSERT INTO supply.conab_production_1m
           (report_month, crop_year, commodity, production_mt, source, row_hash, raw_payload)
           VALUES ($1, $2, 'Soybeans', $3, 'USDA_PSD', $4, $5::jsonb)
           ON CONFLICT (report_month, crop_year, commodity) DO UPDATE SET
             production_mt = EXCLUDED.production_mt`,
          [reportMonth, record.marketYear, value * 1000, rowHash, JSON.stringify(record)]
        );
        inserted++;
        console.log(`   ✅ ${record.marketYear}: ${(value * 1000).toFixed(0)} MT`);
      }
    }
    totalInserted += inserted;
    console.log(`   📊 Inserted: ${inserted} records\n`);
  } catch (e) {
    console.log(`   ❌ Error: ${e.message}\n`);
  }

  // 2. ARGENTINA CRUSH
  console.log('2️⃣  ARGENTINA SOYBEAN CRUSH\n');
  try {
    const arData = await fetchUSDAPSD('AR', '2222'); // Argentina, Soybeans
    console.log(`   Fetched ${arData.length} Argentina records`);

    let inserted = 0;
    for (const record of arData) {
      const year = record.marketYear.split('/')[0];
      const reportMonth = new Date(`${year}-03-01`);
      const rowHash = createHash('sha256').update(`AR|${record.marketYear}|${record.attributeDescription}`).digest('hex');

      const value = parseFloat(record.value);
      if (isNaN(value)) continue;

      if (record.attributeDescription === 'Crush') {
        await pool.query(
          `INSERT INTO supply.argentina_crush_1m
           (report_month, crush_volume_mt, source, row_hash, raw_payload)
           VALUES ($1, $2, 'USDA_PSD', $3, $4::jsonb)
           ON CONFLICT (report_month) DO UPDATE SET
             crush_volume_mt = EXCLUDED.crush_volume_mt`,
          [reportMonth, value * 1000, rowHash, JSON.stringify(record)]
        );
        inserted++;
        console.log(`   ✅ ${record.marketYear}: ${(value * 1000).toFixed(0)} MT crush`);
      }
    }
    totalInserted += inserted;
    console.log(`   📊 Inserted: ${inserted} records\n`);
  } catch (e) {
    console.log(`   ❌ Error: ${e.message}\n`);
  }

  // 3. MALAYSIA PALM OIL PRODUCTION
  console.log('3️⃣  MALAYSIA PALM OIL PRODUCTION (MPOB proxy)\n');
  try {
    const myData = await fetchUSDAPSD('MY', '4243'); // Malaysia, Palm Oil
    console.log(`   Fetched ${myData.length} Malaysia records`);

    let inserted = 0;
    for (const record of myData) {
      const year = record.marketYear.split('/')[0];
      const reportMonth = new Date(`${year}-10-01`);
      const rowHash = createHash('sha256').update(`MY|${record.marketYear}|${record.attributeDescription}`).digest('hex');

      const value = parseFloat(record.value);
      if (isNaN(value)) continue;

      if (record.attributeDescription === 'Production') {
        await pool.query(
          `INSERT INTO supply.mpob_palm_1m
           (report_month, production_mt, country, source, row_hash, raw_payload)
           VALUES ($1, $2, 'Malaysia', 'USDA_PSD', $3, $4::jsonb)
           ON CONFLICT (report_month, country) DO UPDATE SET
             production_mt = EXCLUDED.production_mt`,
          [reportMonth, value * 1000, rowHash, JSON.stringify(record)]
        );
        inserted++;
        console.log(`   ✅ ${record.marketYear}: ${(value * 1000).toFixed(0)} MT`);
      } else if (record.attributeDescription === 'Exports') {
        await pool.query(
          `UPDATE supply.mpob_palm_1m SET exports_mt = $1
           WHERE report_month = $2 AND country = 'Malaysia'`,
          [value * 1000, reportMonth]
        );
      }
    }
    totalInserted += inserted;
    console.log(`   📊 Inserted: ${inserted} records\n`);
  } catch (e) {
    console.log(`   ❌ Error: ${e.message}\n`);
  }

  console.log('='.repeat(70));
  console.log('📊 TOTAL INSERTED:', totalInserted, 'critical supply records');
  console.log('='.repeat(70) + '\n');

  await pool.end();
}

main().catch(e => {
  console.error('FATAL:', e);
  process.exit(1);
});
