/**
 * Run: cd frontend && npx tsx ../scripts/create_zl_live.ts
 */
import { Pool } from 'pg'

const DATABASE_URL = "postgres://d687a7ec267e124a21607a1e5dd9a89d60c9a122d219e499e32f3eee42a858c0:sk_NLg8ZV3VJ61FPM0F_QHMe@db.prisma.io:5432/postgres?sslmode=require"

const pool = new Pool({
  connectionString: DATABASE_URL,
  ssl: { rejectUnauthorized: false },
})

async function main() {
  const client = await pool.connect()
  try {
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
    `)
    console.log('✅ Table analytics.zl_live created')

    // Seed from existing data
    await client.query(`
      INSERT INTO analytics.zl_live (price, previous_close, change, change_pct, day_high, day_low, day_open, volume, timestamp, source, updated_at)
      SELECT price, previous_close, change, change_percent, day_high, day_low, day_open, volume, timestamp, source, updated_at
      FROM public.latest_prices WHERE symbol = 'ZL'
      ON CONFLICT DO NOTHING;
    `)
    console.log('✅ Seeded from public.latest_prices')

    // Verify
    const result = await client.query('SELECT * FROM analytics.zl_live LIMIT 1')
    console.log('✅ Verified:', result.rows[0])

  } finally {
    client.release()
    await pool.end()
  }
}

main().catch(console.error)
