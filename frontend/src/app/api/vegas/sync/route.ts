/**
 * Vegas Glide Sync API
 * POST /api/vegas/sync - Sync data from Glide to PostgreSQL
 *
 * Data Flow: Glide API (READ ONLY) → ops.vegas_* tables
 */
import { NextResponse } from 'next/server'
import { Pool } from 'pg'

// =============================================================================
// Glide API Configuration
// =============================================================================

const GLIDE_API_ENDPOINT = 'https://api.glideapp.io/api/function/queryTables'
const GLIDE_APP_ID = '6nvONp42nj5tLQmMcqF3'
const GLIDE_BEARER_TOKEN = process.env.GLIDE_BEARER_TOKEN || '460c9ee4-edcb-43cc-86b5-929e2bb94351'

// Table IDs from Glide
const GLIDE_TABLES: Record<string, string> = {
  restaurants: 'native-table-ojIjQjDcDAEOpdtZG5Ao',
  casinos: 'native-table-Gy2xHsC7urEttrz80hS7',
  fryers: 'native-table-r2BIqSLhezVbOKGeRJj8',
  export_list: 'native-table-PLujVF4tbbiIi9fzrWg8',
  shifts: 'native-table-K53E3SQsgOUB4wdCJdAN',
}

// =============================================================================
// Glide API Client
// =============================================================================

interface GlideRow {
  [key: string]: unknown
}

async function fetchGlideTable(tableId: string): Promise<GlideRow[]> {
  const response = await fetch(GLIDE_API_ENDPOINT, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${GLIDE_BEARER_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      appID: GLIDE_APP_ID,
      queries: [{ tableName: tableId, utc: true }],
    }),
  })

  if (!response.ok) {
    throw new Error(`Glide API error: ${response.status}`)
  }

  const data = await response.json()
  if (Array.isArray(data) && data.length > 0 && data[0].rows) {
    return data[0].rows
  }
  return []
}

// =============================================================================
// Database Operations
// =============================================================================

async function syncTableToPostgres(
  pool: Pool,
  tableName: string,
  rows: GlideRow[]
): Promise<number> {
  if (rows.length === 0) return 0

  const client = await pool.connect()
  const fullTable = `ops.vegas_${tableName}`

  try {
    await client.query('BEGIN')

    // Create schema if not exists
    await client.query('CREATE SCHEMA IF NOT EXISTS ops')

    // Create table if not exists (id + data JSONB + ingested_at)
    await client.query(`
      CREATE TABLE IF NOT EXISTS ${fullTable} (
        id SERIAL PRIMARY KEY,
        glide_row_id TEXT,
        data JSONB NOT NULL,
        ingested_at TIMESTAMPTZ DEFAULT NOW()
      )
    `)

    // Truncate for full refresh
    await client.query(`TRUNCATE TABLE ${fullTable}`)

    // Insert rows
    for (const row of rows) {
      const glideRowId = row['$rowID'] as string || null
      await client.query(
        `INSERT INTO ${fullTable} (glide_row_id, data, ingested_at) VALUES ($1, $2, NOW())`,
        [glideRowId, JSON.stringify(row)]
      )
    }

    await client.query('COMMIT')
    return rows.length
  } catch (error) {
    await client.query('ROLLBACK')
    throw error
  } finally {
    client.release()
  }
}

// =============================================================================
// POST /api/vegas/sync
// =============================================================================

export async function POST() {
  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: { rejectUnauthorized: false },
  })

  const results: Record<string, number | string> = {}

  try {
    for (const [tableName, tableId] of Object.entries(GLIDE_TABLES)) {
      try {
        console.log(`Syncing ${tableName}...`)
        const rows = await fetchGlideTable(tableId)
        const count = await syncTableToPostgres(pool, tableName, rows)
        results[tableName] = count
        console.log(`✅ ${tableName}: ${count} rows`)
      } catch (error) {
        console.error(`❌ ${tableName}:`, error)
        results[tableName] = `error: ${String(error)}`
      }
    }

    return NextResponse.json({
      success: true,
      synced_at: new Date().toISOString(),
      results,
    })
  } catch (error) {
    return NextResponse.json(
      { success: false, error: String(error) },
      { status: 500 }
    )
  } finally {
    await pool.end()
  }
}

// GET just returns status
export async function GET() {
  return NextResponse.json({
    endpoint: '/api/vegas/sync',
    method: 'POST to sync data from Glide',
    tables: Object.keys(GLIDE_TABLES),
  })
}
