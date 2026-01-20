/**
 * Vegas Restaurants API
 * Returns restaurant data from Glide sync
 */
import { NextResponse } from 'next/server'
import { query } from '@/lib/db'

export async function GET() {
  try {
    const rows = await query<{ id: number; glide_row_id: string; data: Record<string, unknown>; ingested_at: string }>(`
      SELECT id, glide_row_id, data, ingested_at::text
      FROM vegas.vegas_restaurants
      ORDER BY id
      LIMIT 500
    `)

    // Flatten the JSONB data for easier frontend consumption
    const restaurants = rows.map(row => ({
      id: row.id,
      glide_id: row.glide_row_id,
      ingested_at: row.ingested_at,
      ...row.data
    }))

    return NextResponse.json({
      count: restaurants.length,
      data: restaurants
    })

  } catch (error) {
    console.error('Vegas restaurants error:', error)
    return NextResponse.json({ 
      count: 0, 
      data: [],
      error: 'Failed to fetch restaurants' 
    }, { status: 500 })
  }
}
