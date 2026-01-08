// Quick script to create analytics.zl_live table
import pg from 'pg';
const { Client } = pg;

async function main() {
  const client = new Client({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false }
  });
  
  await client.connect();
  
  // Create table
  await client.query(`
    CREATE TABLE IF NOT EXISTS analytics.zl_live (
      id SERIAL PRIMARY KEY,
      price DOUBLE PRECISION NOT NULL,
      previous_close DOUBLE PRECISION,
      change DOUBLE PRECISION,
      change_pct DOUBLE PRECISION,
      day_high DOUBLE PRECISION,
      day_low DOUBLE PRECISION,
      day_open DOUBLE PRECISION,
      volume INTEGER,
      timestamp TIMESTAMPTZ,
      source VARCHAR(50),
      updated_at TIMESTAMPTZ DEFAULT NOW()
    );
  `);
  console.log('✓ Created analytics.zl_live');
  
  // Seed from existing
  const result = await client.query(`
    INSERT INTO analytics.zl_live (price, previous_close, change, change_pct, day_high, day_low, day_open, volume, timestamp, source, updated_at)
    SELECT price, previous_close, change, change_percent, day_high, day_low, day_open, volume, timestamp, source, updated_at
    FROM public.latest_prices WHERE symbol = 'ZL'
    ON CONFLICT DO NOTHING
    RETURNING id;
  `);
  console.log('✓ Seeded from public.latest_prices:', result.rowCount, 'rows');
  
  await client.end();
}

main().catch(console.error);
