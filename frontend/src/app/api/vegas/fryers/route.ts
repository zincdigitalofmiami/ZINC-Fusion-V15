/**
 * Vegas Fryers API
 * Returns fryer capacity data from Glide sync
 * This is FOUNDATION data - all volume calculations depend on this
 */
import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

export async function GET() {
  try {
    const rows = await query<{ id: number; glide_row_id: string; data: Record<string, unknown>; ingested_at: string }>(`
      SELECT id, glide_row_id, data, ingested_at::text
      FROM vegas.vegas_fryers
      ORDER BY id
      LIMIT 1000
    `)

    // Flatten the JSONB data
    const fryers = rows.map(row => ({
      id: row.id,
      glide_id: row.glide_row_id,
      ingested_at: row.ingested_at,
      ...row.data
    }))

    // Calculate totals
    let totalCapacity = 0
    let totalFryers = fryers.length

    return NextResponse.json({
      count: fryers.length,
      total_fryers: totalFryers,
      total_capacity_lbs: totalCapacity,
      data: fryers
    })

  } catch (error) {
    console.error('Vegas fryers error:', error)
    return NextResponse.json({ 
      count: 0, 
      total_fryers: 0,
      total_capacity_lbs: 0,
      data: [],
      error: 'Failed to fetch fryers' 
    }, { status: 500 })
  }
}
