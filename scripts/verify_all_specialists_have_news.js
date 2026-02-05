const { Pool } = require('pg');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const SPECIALISTS = [
  'crush', 'china', 'fx', 'fed', 'tariff', 'energy',
  'biofuel', 'palm', 'volatility', 'substitutes', 'trump_effect'
];

async function verifyAllSpecialistsHaveNews() {
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
  });

  console.log('\n' + '='.repeat(70));
  console.log('🔍 VERIFYING ALL SPECIALISTS GET THEIR TAGGED NEWS/ALT DATA');
  console.log('='.repeat(70) + '\n');

  // Find all tables with specialist_tags
  const tables = await pool.query(`
    SELECT DISTINCT 
      table_schema || '.' || table_name as full_name,
      table_schema,
      table_name
    FROM information_schema.columns
    WHERE column_name = 'specialist_tags'
      AND table_schema IN ('alt', 'econ', 'features')
    ORDER BY table_schema, table_name
  `);

  console.log(`📋 Found ${tables.rowCount} tables with specialist_tags:\n`);
  tables.rows.forEach(t => {
    console.log(`   - ${t.full_name}`);
  });
  console.log('');

  const results = {};

  for (const specialist of SPECIALISTS) {
    console.log(`\n${'='.repeat(70)}`);
    console.log(`🎯 ${specialist.toUpperCase()}`);
    console.log('='.repeat(70));

    let totalArticles = 0;
    const sourceBreakdown = {};

    for (const table of tables.rows) {
      const fullName = table.full_name;

      try {
        const count = await pool.query(`
          SELECT COUNT(*) as count
          FROM ${fullName}
          WHERE '${specialist}' = ANY(specialist_tags)
        `);

        const articleCount = parseInt(count.rows[0].count);
        if (articleCount > 0) {
          sourceBreakdown[fullName] = articleCount;
          totalArticles += articleCount;
        }
      } catch (e) {
        // Skip on error
      }
    }

    if (totalArticles > 0) {
      console.log(`  ✅ Has ${totalArticles} articles from ${Object.keys(sourceBreakdown).length} sources`);
      console.log('\n  Source breakdown:');
      Object.entries(sourceBreakdown)
        .sort((a, b) => b[1] - a[1])
        .forEach(([source, count]) => {
          console.log(`     ${source.padEnd(35)} ${count} articles`);
        });
      
      results[specialist] = { has_data: true, total: totalArticles, sources: Object.keys(sourceBreakdown).length };
    } else {
      console.log(`  ❌ NO ARTICLES FOUND`);
      results[specialist] = { has_data: false, total: 0, sources: 0 };
    }
  }

  console.log('\n' + '='.repeat(70));
  console.log('📈 FINAL SUMMARY');
  console.log('='.repeat(70));

  const withData = Object.values(results).filter(r => r.has_data).length;
  const totalArticles = Object.values(results).reduce((sum, r) => sum + r.total, 0);

  console.log(`\n  Specialists with news data: ${withData}/${SPECIALISTS.length}`);
  console.log(`  Total articles across all:  ${totalArticles}`);

  if (withData === SPECIALISTS.length) {
    console.log('\n  ✅ SUCCESS: ALL 11 SPECIALISTS HAVE THEIR TAGGED NEWS DATA!\n');
  } else {
    const missing = Object.entries(results)
      .filter(([k, v]) => !v.has_data)
      .map(([k]) => k);
    console.log(`\n  ⚠️  Missing data: ${missing.join(', ')}\n`);
  }

  console.log('='.repeat(70) + '\n');

  await pool.end();
}

verifyAllSpecialistsHaveNews().catch(e => {
  console.error('ERROR:', e);
  process.exit(1);
});
