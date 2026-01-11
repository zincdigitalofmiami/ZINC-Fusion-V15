require('dotenv').config({ path: '.env.local' });
const { Pool } = require('pg');
const pool = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });

async function check() {
  const client = await pool.connect();
  
  // Sample rows
  const r = await client.query(
    'SELECT document_number, document_type, title, specialist_tags, event_date FROM raw.legislation_federal_register_1d ORDER BY event_date DESC LIMIT 5'
  );
  console.log('=== Sample Rows ===');
  r.rows.forEach(row => {
    console.log(row.document_number + ' | ' + row.document_type);
    console.log('  Tags: ' + row.specialist_tags.join(', '));
    console.log('  Title: ' + (row.title || '').substring(0, 60) + '...');
    console.log('');
  });
  
  // Tag distribution
  const tags = await client.query(
    'SELECT unnest(specialist_tags) as tag, COUNT(*) as cnt FROM raw.legislation_federal_register_1d GROUP BY 1 ORDER BY 2 DESC'
  );
  console.log('=== Tag Distribution ===');
  tags.rows.forEach(row => console.log('  ' + row.tag + ': ' + row.cnt));
  
  client.release();
  await pool.end();
}
check().catch(console.error);
