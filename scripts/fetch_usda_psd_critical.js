/**
 * Fetch CRITICAL supply data from USDA PSD Online
 * Direct CSV download approach (more reliable than API)
 *
 * PSD Online: https://apps.fas.usda.gov/psdonline/
 */

const { Pool } = require('pg');
const { createHash } = require('crypto');
require('dotenv').config({ path: require('path').join(__dirname, '../frontend/.env.local') });

async function fetchPSDData(commodityCode, countryCode) {
  // Use PSD Online download endpoint (publicly accessible CSV)
  const url = `https://apps.fas.usda.gov/psdonline/downloads/${commodityCode}.csv`;

  console.log(`   Fetching: ${url}`);

  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  const csv = await response.text();
  const lines = csv.split('\n');
  const headers = lines[0].split(',');

  const records = [];
  for (let i = 1; i < lines.length; i++) {
    if (!lines[i].trim()) continue;

    const values = lines[i].split(',');
    const record = {};
    headers.forEach((h, idx) => {
      record[h.trim()] = values[idx]?.trim();
    });

    // Filter for our country
    if (record.Country_Code === countryCode) {
      records.push(record);
    }
  }

  return records;
}

async function main() {
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
  });

  console.log('\n🚨 FETCHING CRITICAL SUPPLY DATA FROM USDA PSD\n');
  console.log('='.repeat(70) + '\n');

  let totalInserted = 0;

  // 1. Brazil Soybeans
  console.log('1️⃣  BRAZIL SOYBEANS (CONAB)\n');
  try {
    const brData = await fetchPSDData('oilseed', 'BR');
    console.log(`   ✅ Downloaded ${brData.length} Brazil records\n`);

    const productionRecords = brData.filter(r =>
      r.Attribute_Description === 'Production' &&
      r.Commodity_Description?.toLowerCase().includes('soybean') &&
      !r.Commodity_Description?.toLowerCase().includes('meal') &&
      !r.Commodity_Description?.toLowerCase().includes('oil')
    );

    console.log(`   Found ${productionRecords.length} production records\n`);

    for (const rec of productionRecords.slice(0, 10)) {
      const year = rec.Market_Year?.split('/')[0];
      if (!year) continue;

      const reportMonth = new Date(`${year}-07-01`);
      const value = parseFloat(rec.Value);
      if (isNaN(value)) continue;

      const rowHash = createHash('sha256').update(`BR|${rec.Market_Year}|Production`).digest('hex');

      await pool.query(
        `INSERT INTO supply.conab_production_1m
         (report_month, crop_year, commodity, production_mt, source, row_hash, raw_payload)
         VALUES ($1, $2, 'Soybeans', $3, 'USDA_PSD', $4, $5::jsonb)
         ON CONFLICT (report_month, crop_year, commodity) DO UPDATE SET production_mt = EXCLUDED.production_mt`,
        [reportMonth, rec.Market_Year, value * 1000, rowHash, JSON.stringify(rec)]
      );

      console.log(`   ✅ ${rec.Market_Year}: ${(value * 1000 / 1000000).toFixed(2)} MMT`);
      totalInserted++;
    }
    console.log('');
  } catch (e) {
    console.log(`   ❌ Error: ${e.message}\n`);
  }

  // 2. Argentina Crush
  console.log('2️⃣  ARGENTINA CRUSH\n');
  try {
    const arData = await fetchPSDData('oilseed', 'AR');
    console.log(`   ✅ Downloaded ${arData.length} Argentina records\n`);

    const crushRecords = arData.filter(r =>
      r.Attribute_Description === 'Crush' &&
      r.Commodity_Description?.toLowerCase().includes('soybean')
    );

    console.log(`   Found ${crushRecords.length} crush records\n`);

    for (const rec of crushRecords.slice(0, 10)) {
      const year = rec.Market_Year?.split('/')[0];
      if (!year) continue;

      const reportMonth = new Date(`${year}-03-01`);
      const value = parseFloat(rec.Value);
      if (isNaN(value)) continue;

      const rowHash = createHash('sha256').update(`AR|${rec.Market_Year}|Crush`).digest('hex');

      await pool.query(
        `INSERT INTO supply.argentina_crush_1m
         (report_month, crush_volume_mt, source, row_hash, raw_payload)
         VALUES ($1, $2, 'USDA_PSD', $3, $4::jsonb)
         ON CONFLICT (report_month) DO UPDATE SET crush_volume_mt = EXCLUDED.crush_volume_mt`,
        [reportMonth, value * 1000, rowHash, JSON.stringify(rec)]
      );

      console.log(`   ✅ ${rec.Market_Year}: ${(value * 1000 / 1000000).toFixed(2)} MMT`);
      totalInserted++;
    }
    console.log('');
  } catch (e) {
    console.log(`   ❌ Error: ${e.message}\n`);
  }

  // 3. Malaysia Palm Oil
  console.log('3️⃣  MALAYSIA PALM OIL (MPOB)\n');
  try {
    const myData = await fetchPSDData('tree_nuts', 'MY');
    console.log(`   ✅ Downloaded ${myData.length} Malaysia records\n`);

    const palmRecords = myData.filter(r =>
      r.Commodity_Description?.toLowerCase().includes('palm') &&
      r.Attribute_Description === 'Production'
    );

    console.log(`   Found ${palmRecords.length} palm production records\n`);

    for (const rec of palmRecords.slice(0, 10)) {
      const year = rec.Market_Year?.split('/')[0];
      if (!year) continue;

      const reportMonth = new Date(`${year}-10-01`);
      const value = parseFloat(rec.Value);
      if (isNaN(value)) continue;

      const rowHash = createHash('sha256').update(`MY|${rec.Market_Year}|Production`).digest('hex');

      await pool.query(
        `INSERT INTO supply.mpob_palm_1m
         (report_month, production_mt, country, source, row_hash, raw_payload)
         VALUES ($1, $2, 'Malaysia', 'USDA_PSD', $3, $4::jsonb)
         ON CONFLICT (report_month, country) DO UPDATE SET production_mt = EXCLUDED.production_mt`,
        [reportMonth, value * 1000, rowHash, JSON.stringify(rec)]
      );

      console.log(`   ✅ ${rec.Market_Year}: ${(value * 1000 / 1000000).toFixed(2)} MMT`);
      totalInserted++;
    }
    console.log('');
  } catch (e) {
    console.log(`   ❌ Error: ${e.message}\n`);
  }

  console.log('='.repeat(70));
  console.log('✅ CRITICAL SUPPLY DATA POPULATED');
  console.log('='.repeat(70));
  console.log(`   Total records: ${totalInserted}`);
  console.log('='.repeat(70) + '\n');

  await pool.end();
}

main().catch(e => console.error('Error:', e));
