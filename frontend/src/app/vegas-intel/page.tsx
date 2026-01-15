'use client'

import { useEffect, useState } from 'react'

/**
 * Vegas Intel Page - Kevin's Sales Command Center
 *
 * SPEC: /Docs/VEGAS_INTEL_SPEC_LOCKED.md
 *
 * Layout:
 * 1. Event Cards (horizontal row, real data from ops.vegas_events)
 * 2. Opportunities (full-width rows, existing customers + prospects from Glide)
 * 3. At Risk (full-width rows, churn alerts - computed from order patterns)
 *
 * ALL DATA IS REAL - No mock data, no fallbacks, no placeholders.
 */

// =============================================================================
// Types
// =============================================================================

interface VegasStats {
  restaurants: number
  casinos: number
  fryers: number
  export_list: number
  last_sync: string | null
}

interface Restaurant {
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

interface VegasEvent {
  id: string
  name: string
  description: string | null
  category: string | null
  venue: string | null
  attendance: number
  startDate: string
  endDate: string | null
  daysUntil: number
  color: string
  // ZFusion scoring (from event intelligence data)
  rank: number | null
  localRank: number | null
  predictedSpend: number | null
  hospitalitySpend: number | null
  // Venue geo
  latitude: number | null
  longitude: number | null
  address: string | null
}

interface Opportunity {
  id: number
  name: string
  casino: string
  contact_person: string | null
  service_frequency: string | null
  status: 'customer' | 'prospect'
  eventMatch: 'HIGH' | 'MEDIUM' | 'LOW'
  fryer_count: number
  total_capacity_lbs: number | null
  oneLiner: string
}

// ZFusion opportunity from the scoring API
interface ZFusionOpportunity {
  restaurant_id: number
  restaurant_name: string
  casino_name: string
  cuisine_type: string
  affinity_score: number
  spend_share: number
  phq_multiplier: number
  zfusion_score: number
  reasoning: string
}

interface ZFusionResponse {
  event: {
    id: string
    category: string
    attendance: number
    rank: number
    localRank: number
    hospitalitySpend: number
    categorySpend: number
    phqMultiplier: number
  }
  opportunities: ZFusionOpportunity[]
  count: number
}

// AtRiskCustomer interface removed - no real data to compute at-risk status yet
// Will be added back when shift/order history data is available from Glide

// =============================================================================
// Status Colors
// =============================================================================

const STATUS_COLORS = {
  customer: '#2dd4bf',  // teal
  prospect: '#b91c1c',  // maroon
}

// =============================================================================
// Main Component
// =============================================================================

export default function VegasIntelPage() {
  const [stats, setStats] = useState<VegasStats | null>(null)
  const [restaurants, setRestaurants] = useState<Restaurant[]>([])
  const [events, setEvents] = useState<VegasEvent[]>([])
  const [loading, setLoading] = useState(true)
  const [eventsLoading, setEventsLoading] = useState(true)
  const [selectedEvent, setSelectedEvent] = useState<string | null>(null)
  const [filter, setFilter] = useState<'all' | 'customers' | 'prospects'>('all')

  // ZFusion scoring state
  const [zfusionData, setZfusionData] = useState<ZFusionResponse | null>(null)
  const [zfusionLoading, setZfusionLoading] = useState(false)

  // Fetch ZFusion scores when event changes
  useEffect(() => {
    async function fetchZFusion() {
      if (!selectedEvent) return

      setZfusionLoading(true)
      try {
        const res = await fetch(`/api/vegas?view=zfusion&eventId=${selectedEvent}`)
        const data = await res.json()
        if (data.opportunities) {
          setZfusionData(data)
        }
      } catch (err) {
        console.error('Failed to fetch ZFusion scores:', err)
      } finally {
        setZfusionLoading(false)
      }
    }

    fetchZFusion()
  }, [selectedEvent])

  useEffect(() => {
    async function fetchData() {
      try {
        // Fetch stats
        const statsRes = await fetch('/api/vegas?view=stats')
        const statsData = await statsRes.json()
        setStats(statsData)

        // Fetch restaurants
        const restRes = await fetch('/api/vegas?view=restaurants')
        const restData = await restRes.json()
        setRestaurants(restData.restaurants || [])
      } catch (err) {
        console.error('Failed to fetch Vegas data:', err)
      } finally {
        setLoading(false)
      }
    }

    async function fetchEvents() {
      try {
        const eventsRes = await fetch('/api/vegas?view=events')
        const eventsData = await eventsRes.json()
        const eventList = eventsData.events || []
        setEvents(eventList)
        // Auto-select first event if available
        if (eventList.length > 0 && !selectedEvent) {
          setSelectedEvent(eventList[0].id)
        }
      } catch (err) {
        console.error('Failed to fetch events:', err)
      } finally {
        setEventsLoading(false)
      }
    }

    fetchData()
    fetchEvents()
  }, [])

  // Transform restaurants into opportunities based on real Glide data
  // Status: customers have service schedules, prospects don't
  const opportunities: Opportunity[] = restaurants.map((r) => {
    const hasServiceSchedule = r.service_frequency && r.service_frequency.trim() !== ''
    const isCustomer = hasServiceSchedule

    // Event match based on fryer capacity (higher capacity = higher event impact)
    const capacityMatch = r.total_capacity_lbs && r.total_capacity_lbs >= 300 ? 'HIGH'
      : r.total_capacity_lbs && r.total_capacity_lbs >= 100 ? 'MEDIUM'
      : 'LOW'

    return {
      id: r.id,
      name: r.name,
      casino: r.casino || 'Las Vegas',
      contact_person: r.contact_person,
      service_frequency: r.service_frequency,
      status: isCustomer ? 'customer' : 'prospect',
      eventMatch: capacityMatch,
      fryer_count: r.fryer_count,
      total_capacity_lbs: r.total_capacity_lbs,
      oneLiner: isCustomer
        ? `${r.fryer_count} fryers (${r.total_capacity_lbs || 0} lbs). Service: ${r.service_frequency}.${r.contact_person ? ` Contact: ${r.contact_person}` : ''}`
        : `${r.fryer_count} fryers (${r.total_capacity_lbs || 0} lbs). Not yet a customer.`,
    }
  })

  // At-risk section removed - requires real shift/order history data to compute
  // Cannot show "days since order" without actual last_order_date from Glide shifts

  // Filter opportunities
  const filteredOpportunities = opportunities.filter(o => {
    if (filter === 'all') return true
    if (filter === 'customers') return o.status === 'customer'
    if (filter === 'prospects') return o.status === 'prospect'
    return true
  })

  const selectedEventData = events.find(e => e.id === selectedEvent)

  // Format spend for headline
  const formatSpendHeadline = (spend: number | null): string => {
    if (!spend) return ''
    if (spend >= 1000000) return `$${(spend / 1000000).toFixed(1)}M in F&B spend projected.`
    if (spend >= 1000) return `$${Math.round(spend / 1000)}K in F&B spend projected.`
    return ''
  }

  const headline = selectedEventData
    ? `${selectedEventData.name} is ${selectedEventData.daysUntil} days out. ${selectedEventData.attendance.toLocaleString()} people. ${formatSpendHeadline(selectedEventData.hospitalitySpend)} Here's your play.`
    : events.length === 0
      ? "Loading upcoming events..."
      : "Select an event to see opportunities."

  return (
    <div className="main-content" style={{ maxWidth: '1400px' }}>

      {/* ================================================================
          PAGE HEADER
          ================================================================ */}
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 700, marginBottom: '8px' }}>
          Vegas Intel
        </h1>
        <p style={{ fontSize: '16px', color: 'rgba(255,255,255,0.6)' }}>
          {headline}
        </p>
        {stats && (
          <p style={{ fontSize: '12px', color: 'rgba(255,255,255,0.4)', marginTop: '4px' }}>
            {stats.restaurants} restaurants │ {stats.casinos} casinos │ {stats.fryers} fryers │ Last sync: {stats.last_sync ? new Date(stats.last_sync).toLocaleDateString() : 'Never'}
          </p>
        )}
      </div>

      {/* ================================================================
          SECTION 1: EVENT CARDS (Real data from ops.vegas_events)
          ================================================================ */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: `repeat(${Math.min(events.length || 4, 4)}, 1fr)`,
        gap: '24px',
        marginBottom: '48px'
      }}>
        {eventsLoading ? (
          <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '40px', opacity: 0.5 }}>
            Loading events...
          </div>
        ) : events.length === 0 ? (
          <div style={{ gridColumn: '1 / -1', textAlign: 'center', padding: '40px', opacity: 0.5 }}>
            No upcoming events found. Check ops.vegas_events table.
          </div>
        ) : (
          events.slice(0, 4).map((event) => (
            <EventCard
              key={event.id}
              event={event}
              selected={selectedEvent === event.id}
              onClick={() => setSelectedEvent(event.id)}
            />
          ))
        )}
      </div>

      {/* ================================================================
          SECTION 2: ZFUSION OPPORTUNITIES (Scored by cuisine affinity + spend)
          ================================================================ */}
      <div style={{ marginBottom: '48px' }}>
        <div style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: '16px'
        }}>
          <h2 style={{
            fontSize: '12px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '1px',
            opacity: 0.6
          }}>
            ZFUSION OPPORTUNITIES {zfusionData ? `(${zfusionData.count})` : ''}
            {zfusionData?.event && (
              <span style={{ marginLeft: '12px', opacity: 0.5, fontWeight: 400 }}>
                {selectedEventData?.category} → ${(zfusionData.event.categorySpend / 1000000).toFixed(1)}M F&B pool
              </span>
            )}
          </h2>
          <FilterToggle value={filter} onChange={setFilter} />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {zfusionLoading ? (
            <LoadingRow />
          ) : !zfusionData || zfusionData.opportunities.length === 0 ? (
            <EmptyRow message="Select an event to see ZFusion opportunities" />
          ) : (
            zfusionData.opportunities.slice(0, 20).map((opp) => (
              <ZFusionRow key={opp.restaurant_id} opportunity={opp} />
            ))
          )}
        </div>
      </div>

      {/* ================================================================
          SECTION 3: AT RISK - Disabled until shift/order data available
          ================================================================ */}
      {/* At-risk detection requires last_order_date from Glide shifts
          to calculate days since order and detect churn patterns.
          Will be enabled when shift data linkage is complete. */}

    </div>
  )
}

// =============================================================================
// EVENT CARD (Real data)
// =============================================================================

function EventCard({
  event,
  selected,
  onClick
}: {
  event: VegasEvent
  selected: boolean
  onClick: () => void
}) {
  // Format F&B spend for display
  const formatSpend = (spend: number | null): string => {
    if (!spend) return '-'
    if (spend >= 1000000) return `$${(spend / 1000000).toFixed(1)}M`
    if (spend >= 1000) return `$${(spend / 1000).toFixed(0)}K`
    return `$${spend}`
  }

  return (
    <div
      onClick={onClick}
      style={{
        background: selected
          ? 'rgba(255, 255, 255, 0.05)'
          : 'rgba(255, 255, 255, 0.02)',
        border: selected
          ? '1px solid rgba(255, 255, 255, 0.2)'
          : '1px solid rgba(255, 255, 255, 0.08)',
        borderLeft: `4px solid ${event.color}`,
        borderRadius: '0px',
        padding: '24px 20px',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
      }}
    >
      {/* Event Name */}
      <div style={{
        fontSize: '13px',
        fontWeight: 600,
        marginBottom: '8px',
        lineHeight: 1.3,
        minHeight: '34px',
      }}>
        {event.name}
      </div>

      {/* Attendance - Hero Number */}
      <div style={{
        fontSize: '36px',
        fontWeight: 700,
        color: event.color,
        lineHeight: 1,
        marginBottom: '4px'
      }}>
        {event.attendance.toLocaleString()}
      </div>
      <div style={{
        fontSize: '10px',
        opacity: 0.5,
        textTransform: 'uppercase',
        letterSpacing: '0.5px',
        marginBottom: '12px'
      }}>
        ATTENDANCE
      </div>

      {/* ZFusion Scoring Row */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        padding: '8px 0',
        borderTop: '1px solid rgba(255,255,255,0.08)',
        marginTop: '8px',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '16px', fontWeight: 600 }}>{event.rank || '-'}</div>
          <div style={{ fontSize: '9px', opacity: 0.5, textTransform: 'uppercase' }}>Rank</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '16px', fontWeight: 600 }}>{event.localRank || '-'}</div>
          <div style={{ fontSize: '9px', opacity: 0.5, textTransform: 'uppercase' }}>Local</div>
        </div>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: '16px', fontWeight: 600, color: '#4ade80' }}>
            {formatSpend(event.hospitalitySpend)}
          </div>
          <div style={{ fontSize: '9px', opacity: 0.5, textTransform: 'uppercase' }}>F&B</div>
        </div>
      </div>

      {/* Date & Venue */}
      <div style={{
        fontSize: '11px',
        opacity: 0.6,
        marginTop: '8px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span>{event.daysUntil} days</span>
        <span style={{
          background: 'rgba(255,255,255,0.1)',
          padding: '2px 6px',
          borderRadius: '2px',
          fontSize: '10px',
        }}>
          {event.category || 'event'}
        </span>
      </div>
      {event.venue && (
        <div style={{
          fontSize: '10px',
          opacity: 0.4,
          marginTop: '6px',
          whiteSpace: 'nowrap',
          overflow: 'hidden',
          textOverflow: 'ellipsis',
        }}>
          {event.venue}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// FILTER TOGGLE
// =============================================================================

function FilterToggle({
  value,
  onChange
}: {
  value: 'all' | 'customers' | 'prospects'
  onChange: (v: 'all' | 'customers' | 'prospects') => void
}) {
  const options = [
    { key: 'all', label: 'All' },
    { key: 'customers', label: 'Customers' },
    { key: 'prospects', label: 'Prospects' },
  ] as const

  return (
    <div style={{
      display: 'flex',
      gap: '4px',
      background: 'rgba(255,255,255,0.05)',
      padding: '4px',
      borderRadius: '4px'
    }}>
      {options.map((opt) => (
        <button
          key={opt.key}
          onClick={() => onChange(opt.key)}
          style={{
            padding: '6px 12px',
            fontSize: '12px',
            fontWeight: 500,
            border: 'none',
            borderRadius: '2px',
            cursor: 'pointer',
            transition: 'all 0.2s ease',
            background: value === opt.key ? 'rgba(255,255,255,0.1)' : 'transparent',
            color: value === opt.key ? '#fff' : 'rgba(255,255,255,0.6)',
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

// =============================================================================
// OPPORTUNITY ROW
// =============================================================================

function OpportunityRow({ opportunity, selectedEvent }: { opportunity: Opportunity; selectedEvent?: VegasEvent }) {
  const isProspect = opportunity.status === 'prospect'
  const accentColor = isProspect ? STATUS_COLORS.prospect : STATUS_COLORS.customer

  return (
    <div style={{
      display: 'flex',
      alignItems: 'stretch',
      background: 'rgba(255, 255, 255, 0.02)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      borderRadius: '0px',
      transition: 'all 0.2s ease',
      overflow: 'hidden',
    }}>
      {/* Left Accent Bar */}
      <div style={{
        width: '4px',
        background: accentColor,
        flexShrink: 0,
      }} />

      {/* Content */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        padding: '20px 24px',
        flex: 1,
      }}>

      {/* Main Content */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '6px'
        }}>
          <span style={{ fontSize: '15px', fontWeight: 600 }}>
            {opportunity.casino} - {opportunity.name}
          </span>
          {isProspect && (
            <span style={{
              fontSize: '10px',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
              padding: '2px 8px',
              background: 'rgba(185, 28, 28, 0.2)',
              color: '#f87171',
              borderRadius: '2px',
            }}>
              PROSPECT
            </span>
          )}
        </div>
        <div style={{
          fontSize: '12px',
          opacity: 0.5,
          marginBottom: '8px'
        }}>
          {selectedEvent ? selectedEvent.name : 'Event'} match: {opportunity.eventMatch} │ {opportunity.fryer_count} fryers ({opportunity.total_capacity_lbs || 0} lbs) │ {opportunity.service_frequency || 'No schedule'}
        </div>
        <div style={{
          fontSize: '13px',
          opacity: 0.7,
          fontStyle: 'italic'
        }}>
          "{opportunity.oneLiner}"
        </div>
      </div>

      {/* Intel Button */}
      <button style={{
        padding: '8px 16px',
        fontSize: '12px',
        fontWeight: 600,
        background: 'transparent',
        border: '1px solid rgba(255,255,255,0.2)',
        borderRadius: '2px',
        color: 'rgba(255,255,255,0.8)',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        flexShrink: 0,
      }}>
        Intel
      </button>
      </div>
    </div>
  )
}

// =============================================================================
// ZFUSION ROW - Scored opportunities with spend share and reasoning
// =============================================================================

function ZFusionRow({ opportunity }: { opportunity: ZFusionOpportunity }) {
  // Color based on ZFusion score
  const scoreColor = opportunity.zfusion_score >= 70 ? '#4ade80' // green
    : opportunity.zfusion_score >= 40 ? '#fbbf24' // yellow
    : '#f87171' // red

  // Format spend share
  const formatSpend = (spend: number): string => {
    if (spend >= 1000000) return `$${(spend / 1000000).toFixed(1)}M`
    if (spend >= 1000) return `$${Math.round(spend / 1000)}K`
    return `$${spend}`
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'stretch',
      background: 'rgba(255, 255, 255, 0.02)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      borderRadius: '0px',
      transition: 'all 0.2s ease',
      overflow: 'hidden',
    }}>
      {/* Left Accent Bar - ZFusion score color */}
      <div style={{
        width: '4px',
        background: scoreColor,
        flexShrink: 0,
      }} />

      {/* Content */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        padding: '16px 24px',
        flex: 1,
      }}>
        {/* ZFusion Score Badge */}
        <div style={{
          width: '56px',
          height: '56px',
          borderRadius: '4px',
          background: `${scoreColor}15`,
          border: `1px solid ${scoreColor}40`,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          flexShrink: 0,
        }}>
          <div style={{ fontSize: '20px', fontWeight: 700, color: scoreColor }}>
            {opportunity.zfusion_score}
          </div>
          <div style={{ fontSize: '8px', opacity: 0.6, textTransform: 'uppercase' }}>
            ZF Score
          </div>
        </div>

        {/* Main Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            marginBottom: '4px'
          }}>
            <span style={{ fontSize: '15px', fontWeight: 600 }}>
              {opportunity.casino_name} - {opportunity.restaurant_name}
            </span>
            <span style={{
              fontSize: '10px',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
              padding: '2px 8px',
              background: 'rgba(255,255,255,0.1)',
              borderRadius: '2px',
            }}>
              {opportunity.cuisine_type}
            </span>
          </div>
          <div style={{
            fontSize: '12px',
            opacity: 0.5,
            marginBottom: '6px'
          }}>
            Affinity: {opportunity.affinity_score}/100 │ PHQ Multiplier: {opportunity.phq_multiplier.toFixed(2)}x
          </div>
          <div style={{
            fontSize: '13px',
            opacity: 0.7,
            fontStyle: 'italic'
          }}>
            "{opportunity.reasoning}"
          </div>
        </div>

        {/* Spend Share */}
        <div style={{
          textAlign: 'right',
          flexShrink: 0,
        }}>
          <div style={{ fontSize: '20px', fontWeight: 700, color: '#4ade80' }}>
            {formatSpend(opportunity.spend_share)}
          </div>
          <div style={{ fontSize: '10px', opacity: 0.5, textTransform: 'uppercase' }}>
            Projected Share
          </div>
        </div>

        {/* Intel Button */}
        <button style={{
          padding: '8px 16px',
          fontSize: '12px',
          fontWeight: 600,
          background: 'transparent',
          border: '1px solid rgba(255,255,255,0.2)',
          borderRadius: '2px',
          color: 'rgba(255,255,255,0.8)',
          cursor: 'pointer',
          transition: 'all 0.2s ease',
          flexShrink: 0,
        }}>
          Intel
        </button>
      </div>
    </div>
  )
}

// =============================================================================
// AT RISK ROW - Disabled until shift/order data available
// =============================================================================
// AtRiskRow component removed - requires real last_order_date data to function

// =============================================================================
// UTILITY COMPONENTS
// =============================================================================

function LoadingRow() {
  return (
    <div style={{
      padding: '40px',
      textAlign: 'center',
      opacity: 0.5,
      background: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.08)',
    }}>
      Loading data from Glide...
    </div>
  )
}

function EmptyRow({ message }: { message: string }) {
  return (
    <div style={{
      padding: '40px',
      textAlign: 'center',
      opacity: 0.5,
      background: 'rgba(255,255,255,0.02)',
      border: '1px solid rgba(255,255,255,0.08)',
    }}>
      {message}
    </div>
  )
}
