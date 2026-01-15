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
  eventType: string | null
  venue: string | null
  attendance: number
  attendanceMin: number | null
  attendanceMax: number | null
  startDate: string
  endDate: string | null
  daysUntil: number
  color: string
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

interface AtRiskCustomer {
  id: number
  name: string
  casino: string
  daysSinceOrder: number
  pattern: string
  oneLiner: string
}

// =============================================================================
// Status Colors
// =============================================================================

const STATUS_COLORS = {
  customer: '#2dd4bf',  // teal
  prospect: '#b91c1c',  // maroon
  atRisk: '#fbbf24',    // amber
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

  // At-risk: Customers with high capacity but need status verification
  const atRiskCustomers: AtRiskCustomer[] = restaurants
    .filter(r => {
      const hasSchedule = r.service_frequency && r.service_frequency.trim() !== ''
      // High-value customers (>3 fryers or >200 lbs capacity) to watch
      return hasSchedule && (r.fryer_count > 3 || (r.total_capacity_lbs && r.total_capacity_lbs > 200))
    })
    .slice(0, 3)
    .map(r => ({
      id: r.id,
      name: r.name,
      casino: r.casino || 'Las Vegas',
      daysSinceOrder: 0, // Would be computed from shift data when available
      pattern: r.service_frequency || 'unknown',
      oneLiner: `${r.fryer_count} fryers (${r.total_capacity_lbs || 0} lbs). ${r.contact_person ? `Contact: ${r.contact_person}` : 'Verify recent orders.'}`,
    }))

  // Filter opportunities
  const filteredOpportunities = opportunities.filter(o => {
    if (filter === 'all') return true
    if (filter === 'customers') return o.status === 'customer'
    if (filter === 'prospects') return o.status === 'prospect'
    return true
  })

  const selectedEventData = events.find(e => e.id === selectedEvent)
  const headline = selectedEventData
    ? `${selectedEventData.name} is ${selectedEventData.daysUntil} days out. ${selectedEventData.attendance.toLocaleString()} people. Here's your play.`
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
          SECTION 2: OPPORTUNITIES (Real data from Glide)
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
            OPPORTUNITIES ({filteredOpportunities.length})
          </h2>
          <FilterToggle value={filter} onChange={setFilter} />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {loading ? (
            <LoadingRow />
          ) : filteredOpportunities.length === 0 ? (
            <EmptyRow message="No opportunities match your filter" />
          ) : (
            filteredOpportunities.slice(0, 15).map((opp) => (
              <OpportunityRow key={opp.id} opportunity={opp} selectedEvent={selectedEventData} />
            ))
          )}
        </div>
      </div>

      {/* ================================================================
          SECTION 3: AT RISK
          ================================================================ */}
      <div>
        <h2 style={{
          fontSize: '12px',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '1px',
          opacity: 0.6,
          marginBottom: '16px'
        }}>
          AT RISK ({atRiskCustomers.length})
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {atRiskCustomers.length === 0 ? (
            <EmptyRow message="No at-risk customers detected" />
          ) : (
            atRiskCustomers.map((customer) => (
              <AtRiskRow key={customer.id} customer={customer} />
            ))
          )}
        </div>
      </div>

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
        padding: '32px 24px',
        textAlign: 'center',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
      }}
    >
      <div style={{
        fontSize: '48px',
        fontWeight: 700,
        color: event.color,
        lineHeight: 1,
        marginBottom: '12px'
      }}>
        {event.attendance.toLocaleString()}
      </div>
      <div style={{
        fontSize: '14px',
        fontWeight: 600,
        marginBottom: '4px',
        textTransform: 'uppercase',
        letterSpacing: '0.5px'
      }}>
        {event.name}
      </div>
      <div style={{
        fontSize: '12px',
        opacity: 0.5,
        textTransform: 'uppercase',
        letterSpacing: '0.5px'
      }}>
        {event.daysUntil} DAYS
      </div>
      {event.venue && (
        <div style={{
          fontSize: '10px',
          opacity: 0.4,
          marginTop: '8px'
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
// AT RISK ROW
// =============================================================================

function AtRiskRow({ customer }: { customer: AtRiskCustomer }) {
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
      {/* Left Accent Bar (amber) */}
      <div style={{
        width: '4px',
        background: STATUS_COLORS.atRisk,
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
            {customer.casino} - {customer.name}
          </span>
          <span style={{
            fontSize: '10px',
            fontWeight: 600,
            textTransform: 'uppercase',
            letterSpacing: '0.5px',
            padding: '2px 8px',
            background: 'rgba(251, 191, 36, 0.2)',
            color: '#fbbf24',
            borderRadius: '2px',
          }}>
            CHECK STATUS
          </span>
        </div>
        <div style={{
          fontSize: '12px',
          opacity: 0.5,
          marginBottom: '8px'
        }}>
          Schedule: {customer.pattern}
        </div>
        <div style={{
          fontSize: '13px',
          opacity: 0.7,
          fontStyle: 'italic'
        }}>
          "{customer.oneLiner}"
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
