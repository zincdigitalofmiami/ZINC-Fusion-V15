/**
 * POPULATE CRITICAL SUPPLY TABLES FROM EXISTING WASDE DATA
 * 
 * We already have Brazil and Argentina data in supply.usda_wasde_1m!
 * Just need to copy it to the specialist-focused tables.
 */

const { Pool } = require('pg');
const { createHash } = require('crypto');
require('dotenv').config({ path: require('path').join(__dirname, '../frontend/.env.local') });

async function main() {
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
  });

  console.log('\n🚨 POPULATING CRITICAL SUPPLY TABLES FROM WASDE\n');
  console.log('='.repeat(70) + '\n');

  // 1. BRAZIL PRODUCTION → conab_production_1m
  console.log('1️⃣  BRAZIL SOYBEAN PRODUCTION → supply.conab_production_1m\n');
  
  const brResult = await pool.query(`
    INSERT INTO supply.conab_production_1m (
      report_month, crop_year, commodity, production_mt, source, row_hash, raw_payload
    )
    SELECT 
      event_date as report_month,
      TO_CHAR(event_date, 'YYYY') || '/' || TO_CHAR(event_date + INTERVAL '1 year', 'YYYY') as crop_year,
      commodity,
      value as production_mt,
      'USDA_WASDE' as source,
      MD5(country || commodity || event_date::text || 'production') as row_hash,
      jsonb_build_object('source', source, 'metric', metric, 'unit', unit, 'value', value) as raw_payload
    FROM supply.usda_wasde_1m
    WHERE country = 'Brazil'
      AND commodity = 'Soybeans'
      AND metric = 'production'
    ON CONFLICT (report_month, crop_year, commodity) DO UPDATE SET
      production_mt = EXCLUDED.production_mt,
      raw_payload = EXCLUDED.raw_payload
    RETURNING report_month, production_mt
  `);
  
  console.log(`   ✅ Inserted ${brResult.rowCount} Brazil production records\n`);
  brResult.rows.slice(0, 5).forEach(r => {
    console.log(`      ${r.report_month.toISOString().split('T')[0]}: ${(r.production_mt / 1000000).toFixed(2)} MMT`);
  });

  // 2. ARGENTINA CRUSH → argentina_crush_1m
  console.log('\n2️⃣  ARGENTINA SOYBEAN CRUSH → supply.argentina_crush_1m\n');
  
  const arCrushResult = await pool.query(`
    INSERT INTO supply.argentina_crush_1m (
      report_month, crush_volume_mt, oil_production_mt, meal_production_mt, 
      source, row_hash, raw_payload
    )
    SELECT 
      event_date as report_month,
      MAX(CASE WHEN commodity = 'Soybeans' AND metric = 'consumption' THEN value END) as crush_volume_mt,
      MAX(CASE WHEN commodity = 'Soybean Oil' AND metric = 'production' THEN value END) as oil_production_mt,
      MAX(CASE WHEN commodity = 'Soybean Meal' AND metric = 'production' THEN value END) as meal_production_mt,
      'USDA_WASDE' as source,
      MD5('Argentina' || event_date::text) as row_hash,
      jsonb_build_object('source', 'USDA_WASDE') as raw_payload
    FROM supply.usda_wasde_1m
    WHERE country = 'Argentina'
      AND commodity IN ('Soybeans', 'Soybean Oil', 'Soybean Meal')
      AND metric IN ('consumption', 'production')
    GROUP BY event_date
    HAVING MAX(CASE WHEN commodity = 'Soybeans' AND metric = 'consumption' THEN value END) IS NOT NULL
    ON CONFLICT (report_month) DO UPDATE SET
      crush_volume_mt = EXCLUDED.crush_volume_mt,
      oil_production_mt = EXCLUDED.oil_production_mt,
      meal_production_mt = EXCLUDED.meal_production_mt
    RETURNING report_month, crush_volume_mt, oil_production_mt
  `);
  
  console.log(`   ✅ Inserted ${arCrushResult.rowCount} Argentina crush records\n`);
  arCrushResult.rows.slice(0, 5).forEach(r => {
    console.log(`      ${r.report_month.toISOString().split('T')[0]}: ${(r.crush_volume_mt / 1000000).toFixed(2)} MMT crush, ${(r.oil_production_mt / 1000000).toFixed(2)} MMT oil`);
  });

  // 3. MALAYSIA PALM - need alternative source (not in WASDE)
  console.log('\n3️⃣  MALAYSIA PALM OIL → supply.mpob_palm_1m\n');
  console.log('   ⚠️  Not in WASDE - will need direct MPOB scraping\n');

  console.log('='.repeat(70));
  console.log('✅ CRITICAL SUPPLY DATA POPULATED (2/3)');
  console.log('='.repeat(70));
  console.log(`   ✅ Brazil production: ${brResult.rowCount} records`);
  console.log(`   ✅ Argentina crush: ${arCrushResult.rowCount} records`);
  console.log(`   ⚠️  Malaysia palm: 0 records (need MPOB source)`);
  console.log('='.repeat(70) + '\n');

  await pool.end();
}

main().catch(e => {
  console.error('FATAL:', e);
  process.exit(1);
});
