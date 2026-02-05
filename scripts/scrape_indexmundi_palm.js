/**
 * Scrape IndexMundi for Malaysia palm oil production data
 * Public data - no API key needed
 * Source: https://www.indexmundi.com/agriculture/?commodity=palm-oil&graph=production
 */

const { Pool } = require('pg');
const { createHash } = require('crypto');
require('dotenv').config({ path: require('path').join(__dirname, '../frontend/.env.local') });

async function scrapePalmProduction() {
  console.log('\n🌴 SCRAPING MALAYSIA PALM OIL PRODUCTION\n');
  console.log('='.repeat(70) + '\n');

  // IndexMundi has production data in their page source
  const url = 'https://www.indexmundi.com/agriculture/?commodity=palm-oil&graph=production&country=my';
  
  console.log('Fetching from IndexMundi...\n');
  
  const response = await fetch(url);
  const html = await response.text();
  
  // Extract data from page (they embed it in JavaScript)
  // Pattern: data points in format [year, value]
  const dataMatch = html.match(/data:\s*\[([\d\s,.\[\]]+)\]/);
  
  if (!dataMatch) {
    console.log('❌ Could not find data in page\n');
    return [];
  }
  
  const dataStr = dataMatch[1];
  const points = JSON.parse(`[${dataStr}]`);
  
  console.log(`✅ Found ${points.length} data points\n`);
  
  const records = [];
  for (const point of points) {
    if (Array.isArray(point) && point.length === 2) {
      const year = parseInt(point[0]);
      const value = parseFloat(point[1]);
      
      if (year >= 2010 && !isNaN(value)) {
        records.push({
          year,
          production_1000mt: value,
          production_mt: value * 1000
        });
      }
    }
  }
  
  return records;
}

async function main() {
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
  });

  try {
    const records = await scrapePalmProduction();
    
    console.log('Inserting into supply.mpob_palm_1m...\n');
    
    let inserted = 0;
    for (const rec of records) {
      const reportMonth = new Date(`${rec.year}-10-01`); // October = marketing year
      const rowHash = createHash('sha256').update(`Malaysia|${rec.year}|IndexMundi`).digest('hex');
      
      await pool.query(
        `INSERT INTO supply.mpob_palm_1m
         (report_month, production_mt, country, source, row_hash, raw_payload)
         VALUES ($1, $2, 'Malaysia', 'IndexMundi', $3, $4::jsonb)
         ON CONFLICT (report_month, country) DO UPDATE SET
           production_mt = EXCLUDED.production_mt`,
        [reportMonth, rec.production_mt, rowHash, JSON.stringify(rec)]
      );
      
      inserted++;
      console.log(`   ✅ ${rec.year}: ${(rec.production_mt / 1000000).toFixed(2)} MMT`);
    }
    
    console.log('\n' + '='.repeat(70));
    console.log('✅ MALAYSIA PALM DATA POPULATED');
    console.log('='.repeat(70));
    console.log(`   Inserted: ${inserted} records`);
    console.log('='.repeat(70) + '\n');
    
  } catch (e) {
    console.error('Error:', e.message);
  } finally {
    await pool.end();
  }
}

main();
