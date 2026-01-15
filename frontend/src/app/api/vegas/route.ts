/**
 * Vegas Intel API Routes
 * Serves data from Glide sync (ops.vegas_* tables)
 * 
 * Data Flow: Glide API (READ ONLY) → ops.vegas_* → This API → Frontend
 */
import { NextResponse } from 'next/server'
import { query } from '@/lib/db'
import {
  assertNoGlideFieldDrift,
  GlideSchemaDriftError,
  VEGAS_GLIDE_FIELDS,
  VEGAS_GLIDE_REQUIRED_FIELDS,
} from '@/lib/vegasGlide'

// =============================================================================
// Types
// =============================================================================

interface VegasStats {
  restaurants: number
  casinos: number
  fryers: number
  export_list: number
  shifts: number
  total_customers: number
  last_sync: string | null
}

interface VegasRestaurant {
  id: number
  glide_row_id: string
  name: string
  casino: string
  contact_person: string | null
  service_frequency: string | null
  oil_type: string | null
  status: string | null
  fryer_count: number
  total_capacity_lbs: number | null
  data: Record<string, unknown>
}

interface VegasCasino {
  id: number
  name: string
  event_calendar: string
  premium_tier: boolean
  data: Record<string, unknown>
}

interface VegasFryer {
  id: number
  restaurant_id: string
  fryer_type: string
  capacity_lb: number
  turns_per_month: number
  base_daily_gal: number
  data: Record<string, unknown>
}

// =============================================================================
// GET /api/vegas - Stats Overview
// =============================================================================

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url)
  const view = searchParams.get('view') || 'stats'

  try {
    switch (view) {
      case 'stats':
        return await getStats()
      case 'restaurants':
        return await getRestaurants()
      case 'casinos':
        return await getCasinos()
      case 'fryers':
        return await getFryers()
      case 'customers':
        return await getCustomers()
      case 'events':
        return await getEvents()
      case 'all':
        return await getAllData()
      default:
        return await getStats()
    }
  } catch (error) {
    console.error('Vegas API error:', error)
    return NextResponse.json(
      { error: 'Failed to fetch Vegas data', details: String(error) },
      { status: 500 }
    )
  }
}

// =============================================================================
// Data Fetchers
// =============================================================================

interface VegasEventRow {
  event_id: string
  name: string
  event_type: string | null
  venue: string | null
  start_date: string
  end_date: string | null
  attendance: number | null
  attendance_min: number | null
  attendance_max: number | null
  days_until: number
}

async function getEvents(): Promise<NextResponse> {
  try {
    // Get upcoming events ordered by start date
    const results = await query<VegasEventRow>(`
      SELECT
        event_id,
        name,
        event_type,
        venue,
        start_date::text,
        end_date::text,
        attendance,
        attendance_min,
        attendance_max,
        (start_date - CURRENT_DATE)::int as days_until
      FROM ops.vegas_events
      WHERE is_active = true
        AND start_date >= CURRENT_DATE
      ORDER BY start_date ASC
      LIMIT 50
    `)

    // Assign colors based on event type
    const getEventColor = (eventType: string | null): string => {
      switch (eventType) {
        case 'CONVENTION_TECH': return '#2962FF'  // blue
        case 'UFC': return '#4ade80'              // green
        case 'F1': return '#ff6b35'               // orange
        case 'EDM_FESTIVAL': return '#a855f7'     // purple
        case 'TRADE_SHOW': return '#14b8a6'       // teal
        case 'SPORTS': return '#22c55e'           // green
        default: return '#6b7280'                 // gray
      }
    }

    const events = results.map(e => ({
      id: e.event_id,
      name: e.name,
      eventType: e.event_type,
      venue: e.venue,
      attendance: e.attendance || e.attendance_min || 0,
      attendanceMin: e.attendance_min,
      attendanceMax: e.attendance_max,
      startDate: e.start_date,
      endDate: e.end_date,
      daysUntil: e.days_until,
      color: getEventColor(e.event_type)
    }))

    return NextResponse.json({ events, count: events.length })
  } catch (error) {
    console.error('getEvents error:', error)
    return NextResponse.json({ events: [], count: 0 })
  }
}

async function getStats(): Promise<NextResponse> {
  try {
    // Get counts from all vegas tables
    const stats = await query<{ table_name: string; count: number; last_sync: string }>(`
      SELECT 
        'restaurants' as table_name,
        COUNT(*) as count,
        MAX(ingested_at)::text as last_sync
      FROM ops.vegas_restaurants
      UNION ALL
      SELECT 
        'casinos' as table_name,
        COUNT(*) as count,
        MAX(ingested_at)::text as last_sync
      FROM ops.vegas_casinos
      UNION ALL
      SELECT 
        'fryers' as table_name,
        COUNT(*) as count,
        MAX(ingested_at)::text as last_sync
      FROM ops.vegas_fryers
      UNION ALL
      SELECT 
        'export_list' as table_name,
        COUNT(*) as count,
        MAX(ingested_at)::text as last_sync
      FROM ops.vegas_export_list
      UNION ALL
      SELECT 
        'shifts' as table_name,
        COUNT(*) as count,
        MAX(ingested_at)::text as last_sync
      FROM ops.vegas_shifts
    `)

    // Parse stats
    const restaurantRow = stats.find(s => s.table_name === 'restaurants')
    const casinoRow = stats.find(s => s.table_name === 'casinos')
    const fryerRow = stats.find(s => s.table_name === 'fryers')
    const exportRow = stats.find(s => s.table_name === 'export_list')
    const shiftRow = stats.find(s => s.table_name === 'shifts')

    const response: VegasStats = {
      restaurants: Number(restaurantRow?.count || 0),
      casinos: Number(casinoRow?.count || 0),
      fryers: Number(fryerRow?.count || 0),
      export_list: Number(exportRow?.count || 0),
      shifts: Number(shiftRow?.count || 0),
      total_customers: Number(restaurantRow?.count || 0) + Number(casinoRow?.count || 0),
      last_sync: restaurantRow?.last_sync || null
    }

    return NextResponse.json(response)

  } catch {
    // Return zeros if tables don't exist yet
    return NextResponse.json({
      restaurants: 0,
      casinos: 0,
      fryers: 0,
      export_list: 0,
      shifts: 0,
      total_customers: 0,
      last_sync: null,
      status: 'not_synced',
      message: 'Run python -m fusion.ingestion.glide_vegas to sync data'
    })
  }
}

async function getRestaurants(): Promise<NextResponse> {
  try {
    const restaurantFields = VEGAS_GLIDE_FIELDS.restaurants
    const fryerFields = VEGAS_GLIDE_FIELDS.fryers

    const results = await query<VegasRestaurant>(`
      SELECT
        r.id,
        r.glide_row_id,
        COALESCE(r.data->>'${restaurantFields.name}', r.data->>'Name', 'Unknown') as name,
        COALESCE(c.data->>'Name', 'Las Vegas') as casino,
        r.data->>'${restaurantFields.primaryContactName}' as contact_person,
        r.data->>'${restaurantFields.scheduleParameters}' as service_frequency,
        r.data->>'${restaurantFields.oilType}' as oil_type,
        r.data->>'${restaurantFields.status}' as status,
        COUNT(f.id)::int as fryer_count,
        SUM((f.data->>'${fryerFields.capacity}')::numeric)::int as total_capacity_lbs,
        r.data
      FROM ops.vegas_restaurants r
      LEFT JOIN ops.vegas_casinos c ON c.glide_row_id = r.data->>'${restaurantFields.casinoId}'
      LEFT JOIN ops.vegas_fryers f ON f.data->>'${fryerFields.restaurantId}' = r.glide_row_id
      GROUP BY r.id, r.glide_row_id, r.data, c.data->>'Name'
      ORDER BY name
      LIMIT 200
    `)

    assertNoGlideFieldDrift({
      entity: 'ops.vegas_restaurants',
      rows: results.map((r) => r.data),
      requiredFields: VEGAS_GLIDE_REQUIRED_FIELDS.restaurants,
      hint: 'Update frontend/src/lib/vegasGlide.ts with the new Glide field IDs.',
    })

    return NextResponse.json({ restaurants: results, count: results.length })
  } catch (error) {
    console.error('getRestaurants error:', error)
    if (error instanceof GlideSchemaDriftError) {
      return NextResponse.json(
        {
          error: 'Glide schema drift detected',
          entity: error.entity,
          missing_fields: error.missingFields,
          details: error.message,
        },
        { status: 500 }
      )
    }

    return NextResponse.json({ restaurants: [], count: 0 })
  }
}

async function getCasinos(): Promise<NextResponse> {
  try {
    const results = await query<VegasCasino>(`
      SELECT
        id,
        COALESCE(data->>'Name', data->>'name', 'Unknown') as name,
        COALESCE(data->>'EventCalendar', data->>'event_calendar', '') as event_calendar,
        COALESCE((data->>'PremiumTier')::boolean, false) as premium_tier,
        data
      FROM ops.vegas_casinos
      ORDER BY name
      LIMIT 100
    `)

    return NextResponse.json({ casinos: results, count: results.length })
  } catch {
    return NextResponse.json({ casinos: [], count: 0 })
  }
}

async function getFryers(): Promise<NextResponse> {
  try {
    const results = await query<VegasFryer>(`
      SELECT
        id,
        COALESCE(data->>'restaurant_id', data->>'RestaurantId', '') as restaurant_id,
        COALESCE(data->>'fryer_type', data->>'FryerType', 'Standard') as fryer_type,
        COALESCE((data->>'capacity_lb')::float, 0) as capacity_lb,
        COALESCE((data->>'turns_per_month')::int, 0) as turns_per_month,
        COALESCE((data->>'base_daily_gal')::float, 0) as base_daily_gal,
        data
      FROM ops.vegas_fryers
      ORDER BY restaurant_id
      LIMIT 500
    `)

    return NextResponse.json({ fryers: results, count: results.length })
  } catch {
    return NextResponse.json({ fryers: [], count: 0 })
  }
}

async function getCustomers(): Promise<NextResponse> {
  try {
    const results = await query<{ id: number; customer_name: string; segment: string; data: Record<string, unknown> }>(`
      SELECT
        id,
        COALESCE(data->>'CustomerName', data->>'customer_name', data->>'Name', 'Unknown') as customer_name,
        COALESCE(data->>'Segment', data->>'segment', 'General') as segment,
        data
      FROM ops.vegas_export_list
      ORDER BY customer_name
      LIMIT 500
    `)

    return NextResponse.json({ customers: results, count: results.length })
  } catch {
    return NextResponse.json({ customers: [], count: 0 })
  }
}

async function getAllData(): Promise<NextResponse> {
  try {
    const [stats, restaurants, casinos, fryers] = await Promise.all([
      query<{ table_name: string; count: number }>(`
        SELECT 'restaurants' as table_name, COUNT(*) as count FROM ops.vegas_restaurants
        UNION ALL
        SELECT 'casinos', COUNT(*) FROM ops.vegas_casinos
        UNION ALL
        SELECT 'fryers', COUNT(*) FROM ops.vegas_fryers
      `),
      query(`SELECT id, data FROM ops.vegas_restaurants LIMIT 10`),
      query(`SELECT id, data FROM ops.vegas_casinos LIMIT 10`),
      query(`SELECT id, data FROM ops.vegas_fryers LIMIT 20`)
    ])

    return NextResponse.json({
      stats: stats.reduce((acc, row) => ({ ...acc, [row.table_name]: row.count }), {}),
      sample: { restaurants, casinos, fryers }
    })
  } catch {
    return NextResponse.json({
      stats: { restaurants: 0, casinos: 0, fryers: 0 },
      sample: { restaurants: [], casinos: [], fryers: [] }
    })
  }
}
