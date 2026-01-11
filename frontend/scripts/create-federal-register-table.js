const { Pool } = require('pg');
require('dotenv').config({ path: '.env.local' });

const pool = new Pool({ 
  connectionString: process.env.DATABASE_URL, 
  ssl: { rejectUnauthorized: false } 
});

async function createTable() {
  const client = await pool.connect();
  
  try {
    // Create table SQL inline
    const sql = `
      CREATE TABLE IF NOT EXISTS raw.legislation_federal_register_1d (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        event_date DATE NOT NULL,
        document_number TEXT NOT NULL,
        document_type TEXT,
        title TEXT,
        abstract TEXT,
        agency TEXT[],
        publication_date DATE,
        effective_date DATE,
        knowledge_time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        revision_no INTEGER NOT NULL DEFAULT 1,
        supersedes_id UUID REFERENCES raw.legislation_federal_register_1d(id),
        is_preliminary BOOLEAN DEFAULT false,
        validation_status TEXT DEFAULT 'valid',
        quality_score NUMERIC(3,2) DEFAULT 1.0,
        anomaly_flags TEXT[] DEFAULT '{}',
        source_url TEXT,
        raw_payload JSONB,
        ingestion_batch_id UUID,
        row_hash TEXT NOT NULL,
        specialist_tags TEXT[] NOT NULL
      );
      CREATE INDEX IF NOT EXISTS idx_fed_reg_row_hash ON raw.legislation_federal_register_1d(row_hash);
      CREATE INDEX IF NOT EXISTS idx_fed_reg_tags ON raw.legislation_federal_register_1d USING GIN(specialist_tags);
      CREATE INDEX IF NOT EXISTS idx_fed_reg_event_date ON raw.legislation_federal_register_1d(event_date);
      CREATE INDEX IF NOT EXISTS idx_fed_reg_doc_number ON raw.legislation_federal_register_1d(document_number);
    `;
    
    // Execute SQL
    await client.query(sql);
    console.log('✅ Table and indexes created');
    
    // Verify
    const r = await client.query(
      "SELECT column_name, data_type FROM information_schema.columns WHERE table_schema = 'raw' AND table_name = 'legislation_federal_register_1d' ORDER BY ordinal_position"
    );
    console.log('\n=== Table columns ===');
    r.rows.forEach(row => console.log(`  ${row.column_name}: ${row.data_type}`));
    
  } finally {
    client.release();
    await pool.end();
  }
}

createTable().catch(console.error);
