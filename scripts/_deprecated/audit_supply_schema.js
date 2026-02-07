const { Pool } = require('pg');
require('dotenv').config({ path: require('path').join(__dirname, '../frontend/.env.local') });

async function auditSupply() {
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
  });

  console.log('\n🔍 AUDITING supply SCHEMA\n');
  console.log('='.repeat(70) + '\n');

  // Get all tables
  const tables = await pool.query(`
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'supply'
      AND table_type = 'BASE TABLE'
    ORDER BY table_name
  `);

  console.log(`📊 Tables in supply schema (${tables.rowCount} total):\n`);

  for (const t of tables.rows) {
    const tableName = t.table_name;
    
    // Get row count
    const count = await pool.query(`SELECT COUNT(*) as count FROM supply.${tableName}`);
    
    // Get columns
    const cols = await pool.query(`
      SELECT column_name, data_type
      FROM information_schema.columns
      WHERE table_schema = 'supply' AND table_name = $1
      ORDER BY ordinal_position
      LIMIT 8
    `, [tableName]);
    
    const colList = cols.rows.map(c => c.column_name).join(', ');
    
    console.log(`   ${tableName.padEnd(30)} ${count.rows[0].count.toString().padStart(6)} rows`);
    console.log(`      Key columns: ${colList}`);
    
    // Get date range if has event_date
    try {
      const dates = await pool.query(`
        SELECT 
          MIN(event_date) as earliest,
          MAX(event_date) as latest
        FROM supply.${tableName}
      `);
      
      if (dates.rows[0].earliest) {
        console.log(`      Date range: ${dates.rows[0].earliest.toISOString().split('T')[0]} to ${dates.rows[0].latest.toISOString().split('T')[0]}`);
      }
    } catch (e) {
      // No event_date column
    }
    
    console.log('');
  }

  console.log('='.repeat(70));
  console.log('💡 ANALYSIS\n');
  console.log('Expected supply tables:');
  console.log('   ✓ usda_wasde_1m - USDA WASDE reports (monthly)');
  console.log('   ✓ epa_rin_1d - EPA RIN prices (biofuel)');
  console.log('   ✓ lcfs_1d - California LCFS credits');
  console.log('   ✓ eia_biodiesel_1m - EIA biodiesel production (monthly)');
  console.log('\\nMissing/Needed:');
  console.log('   ? USDA export sales (weekly) - might be in different schema');
  console.log('   ? Brazil/Argentina production (CONAB) - might be in alt');
  console.log('   ? Palm oil production (MPOB Malaysia) - might be missing');
  console.log('='.repeat(70) + '\n');

  await pool.end();
}

auditSupply().catch(e => console.error('Error:', e));
