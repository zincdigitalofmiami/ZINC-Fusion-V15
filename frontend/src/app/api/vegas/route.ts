/**
 * Vegas Intel API Routes
 * Serves data from Glide sync (vegas.vegas_* tables)
 *
 * Data Flow: Glide API (READ ONLY) → vegas.vegas_* → This API → Frontend
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
  const eventId = searchParams.get('eventId')

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
      case 'zfusion':
        // ZFusion scoring for a specific event
        if (!eventId) {
          return NextResponse.json({ error: 'eventId parameter required' }, { status: 400 })
        }
        return await getZFusionScores(eventId)
      case 'daily-spend':
        // Daily F&B spend forecast
        return await getDailySpend()
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
  category: string | null
  venue: string | null
  start_date: string
  end_date: string | null
  attendance: number | null
  days_until: number
  // Venue geo
  latitude: number | null
  longitude: number | null
  formatted_address: string | null
}

// Color mapping for event categories (from loaded data)
const EVENT_COLORS: Record<string, string> = {
  'expos': '#2962FF',           // blue - conventions, trade shows
  'conferences': '#14b8a6',     // teal
  'concerts': '#a855f7',        // purple
  'sports': '#22c55e',          // green
  'festivals': '#ff6b35',       // orange
  'performing-arts': '#f59e0b', // amber
  'community': '#06b6d4',       // cyan
  'school-holidays': '#ec4899', // pink
}

async function getEvents(): Promise<NextResponse> {
  try {
    // Get upcoming events ordered by attendance (actual schema columns only)
    const results = await query<VegasEventRow>(`
      SELECT
        e.event_id,
        e.name,
        e.event_type as category,
        e.venue,
        e.start_date::text,
        e.end_date::text,
        e.attendance,
        (e.start_date - CURRENT_DATE)::int as days_until,
        v.latitude::float as latitude,
        v.longitude::float as longitude,
        v.formatted_address
      FROM vegas.vegas_events e
      LEFT JOIN vegas.vegas_event_venues ev ON ev.event_id = e.event_id AND ev.is_primary = true
      LEFT JOIN vegas.vegas_venues v ON v.venue_id = ev.venue_id
      WHERE e.is_active = true
        AND e.start_date >= CURRENT_DATE
      ORDER BY e.attendance DESC NULLS LAST, e.start_date ASC
      LIMIT 50
    `)

    const events = results.map(e => ({
      id: e.event_id,
      name: e.name,
      category: e.category,
      venue: e.venue,
      attendance: e.attendance || 0,
      startDate: e.start_date,
      endDate: e.end_date,
      daysUntil: e.days_until,
      color: EVENT_COLORS[e.category || ''] || '#6b7280',
      latitude: e.latitude,
      longitude: e.longitude,
      address: e.formatted_address,
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
      FROM vegas.vegas_restaurants
      UNION ALL
      SELECT
        'casinos' as table_name,
        COUNT(*) as count,
        MAX(ingested_at)::text as last_sync
      FROM vegas.vegas_casinos
      UNION ALL
      SELECT
        'fryers' as table_name,
        COUNT(*) as count,
        MAX(ingested_at)::text as last_sync
      FROM vegas.vegas_fryers
      UNION ALL
      SELECT
        'export_list' as table_name,
        COUNT(*) as count,
        MAX(ingested_at)::text as last_sync
      FROM vegas.vegas_export_list
      UNION ALL
      SELECT
        'shifts' as table_name,
        COUNT(*) as count,
        MAX(ingested_at)::text as last_sync
      FROM vegas.vegas_shifts
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
      FROM vegas.vegas_restaurants r
      LEFT JOIN vegas.vegas_casinos c ON c.glide_row_id = r.data->>'${restaurantFields.casinoId}'
      LEFT JOIN vegas.vegas_fryers f ON f.data->>'${fryerFields.restaurantId}' = r.glide_row_id
      GROUP BY r.id, r.glide_row_id, r.data, c.data->>'Name'
      ORDER BY name
      LIMIT 200
    `)

    assertNoGlideFieldDrift({
      entity: 'vegas.vegas_restaurants',
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
      FROM vegas.vegas_casinos
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
      FROM vegas.vegas_fryers
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
      FROM vegas.vegas_export_list
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
        SELECT 'restaurants' as table_name, COUNT(*) as count FROM vegas.vegas_restaurants
        UNION ALL
        SELECT 'casinos', COUNT(*) FROM vegas.vegas_casinos
        UNION ALL
        SELECT 'fryers', COUNT(*) FROM vegas.vegas_fryers
      `),
      query(`SELECT id, data FROM vegas.vegas_restaurants LIMIT 10`),
      query(`SELECT id, data FROM vegas.vegas_casinos LIMIT 10`),
      query(`SELECT id, data FROM vegas.vegas_fryers LIMIT 20`)
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

// =============================================================================
// ZFusion Scoring - Calculate opportunity scores for restaurants
// Formula: Expected Spend × Cuisine Affinity × PHQ Signal → ZFusion Score
// =============================================================================

interface ZFusionOpportunity {
  restaurant_id: number
  restaurant_name: string
  casino_name: string
  cuisine_type: string
  affinity_score: number
  spend_share: number        // Restaurant's projected share of F&B spend
  phq_multiplier: number     // 0.5-2.0 based on rank/local_rank
  zfusion_score: number      // Final composite score
  reasoning: string          // Why this restaurant benefits
}

async function getZFusionScores(eventId: string): Promise<NextResponse> {
  try {
    // Get the event details first
    const eventResults = await query<{
      event_id: string
      category: string
      attendance: number
      start_date: string
    }>(`
      SELECT
        event_id,
        event_type as category,
        attendance,
        start_date::text
      FROM vegas.vegas_events
      WHERE event_id = $1
    `, [eventId])

    if (eventResults.length === 0) {
      return NextResponse.json({ error: 'Event not found' }, { status: 404 })
    }

    const event = eventResults[0]
    const eventCategory = event.category || 'concerts' // Default fallback

    // Get daily spend for this event's date and category
    const spendResults = await query<{
      spend_concerts: number
      spend_conferences: number
      spend_expos: number
      spend_festivals: number
      spend_performing_arts: number
      spend_sports: number
      spend_total: number
    }>(`
      SELECT
        spend_concerts, spend_conferences, spend_expos,
        spend_festivals, spend_performing_arts, spend_sports,
        spend_total
      FROM vegas.vegas_daily_spend
      WHERE impact_date = $1::date
    `, [event.start_date])

    // Get the category-specific spend
    let categorySpend = 0
    if (spendResults.length > 0) {
      const spendMap: Record<string, number> = {
        'concerts': spendResults[0].spend_concerts,
        'conferences': spendResults[0].spend_conferences,
        'expos': spendResults[0].spend_expos,
        'festivals': spendResults[0].spend_festivals,
        'performing-arts': spendResults[0].spend_performing_arts,
        'sports': spendResults[0].spend_sports,
      }
      categorySpend = spendMap[eventCategory] || categorySpend
    }

    // Calculate PHQ multiplier based on attendance (rank/local_rank not yet in schema)
    // Scale attendance to a 0.5-2.0 multiplier range
    const attendanceScore = Math.min(100000, event.attendance || 5000) / 100000
    const phqMultiplier = 0.5 + (attendanceScore * 1.5) // 0.5 to 2.0 range

    // Get all restaurants with their cuisine types and calculate ZFusion scores
    const restaurantFields = VEGAS_GLIDE_FIELDS.restaurants

    const opportunities = await query<ZFusionOpportunity>(`
      WITH cuisine_totals AS (
        -- Get sum of affinity scores for this event category (for proportional distribution)
        SELECT SUM(affinity_score) as total_affinity
        FROM vegas.vegas_cuisine_affinity
        WHERE event_category = $1
      ),
      restaurant_scores AS (
        SELECT
          r.id as restaurant_id,
          COALESCE(r.data->>'${restaurantFields.name}', 'Unknown') as restaurant_name,
          COALESCE(c.data->>'Name', 'Las Vegas') as casino_name,
          COALESCE(r.cuisine_type, 'general') as cuisine_type,
          COALESCE(ca.affinity_score, 30) as affinity_score,
          ca.reasoning,
          ct.total_affinity
        FROM vegas.vegas_restaurants r
        LEFT JOIN vegas.vegas_casinos c ON c.glide_row_id = r.data->>'${restaurantFields.casinoId}'
        LEFT JOIN vegas.vegas_cuisine_affinity ca
          ON ca.cuisine_type = COALESCE(r.cuisine_type, 'general')
          AND ca.event_category = $1
        CROSS JOIN cuisine_totals ct
        WHERE r.cuisine_type IS NOT NULL
          AND r.cuisine_type != 'service'  -- Exclude back-of-house operations
      )
      SELECT
        restaurant_id,
        restaurant_name,
        casino_name,
        cuisine_type,
        affinity_score,
        -- Spend share = (affinity / total_affinity) × category_spend
        ROUND(
          (affinity_score::float / NULLIF(total_affinity, 0)::float) * $2
        )::integer as spend_share,
        $3::float as phq_multiplier,
        -- ZFusion Score = spend_share × phq_multiplier (normalized to 0-100)
        ROUND(
          LEAST(100,
            ((affinity_score::float / NULLIF(total_affinity, 0)::float) * $2 / 10000) * $3
          )
        )::integer as zfusion_score,
        COALESCE(reasoning, 'General dining option') as reasoning
      FROM restaurant_scores
      ORDER BY zfusion_score DESC, affinity_score DESC
      LIMIT 50
    `, [eventCategory, categorySpend, phqMultiplier])

    return NextResponse.json({
      event: {
        id: event.event_id,
        category: eventCategory,
        attendance: event.attendance,
        categorySpend,
        phqMultiplier: Math.round(phqMultiplier * 100) / 100,
      },
      opportunities,
      count: opportunities.length,
    })

  } catch (error) {
    console.error('getZFusionScores error:', error)
    return NextResponse.json({ error: 'Failed to calculate ZFusion scores', details: String(error) }, { status: 500 })
  }
}

// =============================================================================
// Daily Spend Summary - For dashboard sparklines and heat calendar
// =============================================================================

interface DailySpendRow {
  impact_date: string
  spend_concerts: number
  spend_conferences: number
  spend_expos: number
  spend_festivals: number
  spend_performing_arts: number
  spend_sports: number
  spend_total: number
  top_category: string
  event_count: number
}

async function getDailySpend(): Promise<NextResponse> {
  try {
    const results = await query<DailySpendRow>(`
      SELECT
        ds.impact_date::text,
        ds.spend_concerts,
        ds.spend_conferences,
        ds.spend_expos,
        ds.spend_festivals,
        ds.spend_performing_arts,
        ds.spend_sports,
        ds.spend_total,
        -- Find the dominant category for each day
        CASE
          WHEN GREATEST(spend_concerts, spend_conferences, spend_expos, spend_festivals, spend_performing_arts, spend_sports) = spend_expos THEN 'expos'
          WHEN GREATEST(spend_concerts, spend_conferences, spend_expos, spend_festivals, spend_performing_arts, spend_sports) = spend_concerts THEN 'concerts'
          WHEN GREATEST(spend_concerts, spend_conferences, spend_expos, spend_festivals, spend_performing_arts, spend_sports) = spend_sports THEN 'sports'
          WHEN GREATEST(spend_concerts, spend_conferences, spend_expos, spend_festivals, spend_performing_arts, spend_sports) = spend_conferences THEN 'conferences'
          WHEN GREATEST(spend_concerts, spend_conferences, spend_expos, spend_festivals, spend_performing_arts, spend_sports) = spend_festivals THEN 'festivals'
          ELSE 'performing-arts'
        END as top_category,
        -- Count events for this day
        COALESCE((
          SELECT COUNT(DISTINCT event_id)::int
          FROM vegas.vegas_events
          WHERE start_date = ds.impact_date
            AND is_active = true
        ), 0) as event_count
      FROM vegas.vegas_daily_spend ds
      WHERE ds.impact_date >= CURRENT_DATE
      ORDER BY ds.impact_date
      LIMIT 90
    `)

    // Calculate summary stats
    const totalSpend = results.reduce((sum, r) => sum + (r.spend_total || 0), 0)
    const avgDailySpend = results.length > 0 ? Math.round(totalSpend / results.length) : 0
    const peakDay = results.length > 0
      ? results.reduce((max, r) => (r.spend_total || 0) > (max.spend_total || 0) ? r : max, results[0])
      : null

    return NextResponse.json({
      daily: results.map(r => ({
        date: r.impact_date,
        total: r.spend_total,
        concerts: r.spend_concerts,
        conferences: r.spend_conferences,
        expos: r.spend_expos,
        festivals: r.spend_festivals,
        performingArts: r.spend_performing_arts,
        sports: r.spend_sports,
        topCategory: r.top_category,
        eventCount: r.event_count,
        color: EVENT_COLORS[r.top_category] || '#6b7280',
      })),
      summary: {
        totalSpend,
        avgDailySpend,
        peakDay: peakDay ? {
          date: peakDay.impact_date,
          spend: peakDay.spend_total,
          category: peakDay.top_category,
        } : null,
        daysLoaded: results.length,
      },
    })

  } catch (error) {
    console.error('getDailySpend error:', error)
    return NextResponse.json({ daily: [], summary: null })
  }
}
