'use client'

import { useEffect, useState } from 'react'

/**
 * Vegas Intel Page - Kevin's Sales Command Center
 *
 * Layout:
 * 1. Segment Cards (4 clickable filters with stats)
 * 2. Upcoming Events (PredictHQ-style rows with rank/local/attendance)
 * 3. Opportunities (restaurants - filtered by selected segment)
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
  category: string | null
  venue: string | null
  attendance: number
  startDate: string
  endDate: string | null
  daysUntil: number
  color: string
  rank: number | null
  localRank: number | null
}

interface Opportunity {
  id: number
  name: string
  casino: string
  contact_person: string | null
  service_frequency: string | null
  status: 'customer' | 'prospect'
  fryer_count: number
  total_capacity_lbs: number | null
}

type FilterSegment = 'all' | 'customers' | 'prospects' | 'events'

// =============================================================================
// Status Colors
// =============================================================================

const STATUS_COLORS = {
  customer: '#2dd4bf',
  prospect: '#b91c1c',
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
  const [activeSegment, setActiveSegment] = useState<FilterSegment>('all')

  useEffect(() => {
    async function fetchData() {
      try {
        const statsRes = await fetch('/api/vegas?view=stats')
        const statsData = await statsRes.json()
        setStats(statsData)

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
        let eventList = eventsData.events || []
        // Sort by soonest first
        eventList = eventList.sort((a: VegasEvent, b: VegasEvent) => a.daysUntil - b.daysUntil)
        setEvents(eventList)
      } catch (err) {
        console.error('Failed to fetch events:', err)
      } finally {
        setEventsLoading(false)
      }
    }

    fetchData()
    fetchEvents()
  }, [])

  // Transform restaurants into opportunities
  const opportunities: Opportunity[] = restaurants.map((r) => {
    const hasServiceSchedule = r.service_frequency && r.service_frequency.trim() !== ''
    return {
      id: r.id,
      name: r.name,
      casino: r.casino || 'Las Vegas',
      contact_person: r.contact_person,
      service_frequency: r.service_frequency,
      status: hasServiceSchedule ? 'customer' : 'prospect',
      fryer_count: r.fryer_count,
      total_capacity_lbs: r.total_capacity_lbs,
    }
  })

  // Segment Stats
  const customers = opportunities.filter(o => o.status === 'customer')
  const prospects = opportunities.filter(o => o.status === 'prospect')

  const customerStats = {
    count: customers.length,
    fryers: customers.reduce((sum, c) => sum + c.fryer_count, 0),
    capacity: customers.reduce((sum, c) => sum + (c.total_capacity_lbs || 0), 0),
  }

  const prospectStats = {
    count: prospects.length,
    fryers: prospects.reduce((sum, c) => sum + c.fryer_count, 0),
    capacity: prospects.reduce((sum, c) => sum + (c.total_capacity_lbs || 0), 0),
  }

  const totalStats = {
    count: opportunities.length,
    fryers: opportunities.reduce((sum, c) => sum + c.fryer_count, 0),
    capacity: opportunities.reduce((sum, c) => sum + (c.total_capacity_lbs || 0), 0),
  }

  const eventStats = {
    count: events.length,
    attendance: events.reduce((sum, e) => sum + e.attendance, 0),
    next7Days: events.filter(e => e.daysUntil <= 7).length,
  }

  // Filter opportunities based on active segment
  const filteredOpportunities = opportunities.filter(o => {
    if (activeSegment === 'all') return true
    if (activeSegment === 'customers') return o.status === 'customer'
    if (activeSegment === 'prospects') return o.status === 'prospect'
    if (activeSegment === 'events') return true // Show all when events is selected
    return true
  })

  return (
    <div className="main-content" style={{ maxWidth: '1400px' }}>

      {/* PAGE HEADER */}
      <div style={{ marginBottom: '32px' }}>
        <h1 style={{ fontSize: '32px', fontWeight: 700, marginBottom: '8px' }}>
          Vegas Intel
        </h1>
        <p style={{ fontSize: '16px', color: 'rgba(255,255,255,0.6)' }}>
          Kevin's sales command center. Real data from Glide + PredictHQ.
        </p>
        {stats && (
          <p style={{ fontSize: '12px', color: 'rgba(255,255,255,0.4)', marginTop: '4px' }}>
            Last sync: {stats.last_sync ? new Date(stats.last_sync).toLocaleDateString() : 'Never'}
          </p>
        )}
      </div>

      {/* SECTION 1: SEGMENT FILTER CARDS */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        gap: '12px',
        marginBottom: '48px'
      }}>
        <SegmentCard
          label="ALL ACCOUNTS"
          active={activeSegment === 'all'}
          onClick={() => setActiveSegment('all')}
          color="#3b82f6"
          mainValue={totalStats.count}
          stats={[
            { label: 'Fryers', value: totalStats.fryers },
            { label: 'Capacity', value: `${totalStats.capacity.toLocaleString()} lbs` },
          ]}
        />
        <SegmentCard
          label="CUSTOMERS"
          active={activeSegment === 'customers'}
          onClick={() => setActiveSegment('customers')}
          color="#2dd4bf"
          mainValue={customerStats.count}
          stats={[
            { label: 'Fryers', value: customerStats.fryers },
            { label: 'Capacity', value: `${customerStats.capacity.toLocaleString()} lbs` },
          ]}
        />
        <SegmentCard
          label="PROSPECTS"
          active={activeSegment === 'prospects'}
          onClick={() => setActiveSegment('prospects')}
          color="#ef4444"
          mainValue={prospectStats.count}
          stats={[
            { label: 'Fryers', value: prospectStats.fryers },
            { label: 'Potential', value: `${prospectStats.capacity.toLocaleString()} lbs` },
          ]}
        />
        <SegmentCard
          label="UPCOMING EVENTS"
          active={activeSegment === 'events'}
          onClick={() => setActiveSegment('events')}
          color="#a855f7"
          mainValue={eventStats.count}
          stats={[
            { label: 'Attendance', value: eventStats.attendance.toLocaleString() },
            { label: 'Next 7 Days', value: eventStats.next7Days },
          ]}
        />
      </div>

      {/* SECTION 2: UPCOMING EVENTS - PredictHQ Style */}
      <div style={{ marginBottom: '48px' }}>
        <h2 style={{
          fontSize: '12px',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '1px',
          opacity: 0.6,
          marginBottom: '16px'
        }}>
          UPCOMING EVENTS ({events.length})
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
          {eventsLoading ? (
            <LoadingRow />
          ) : events.length === 0 ? (
            <EmptyRow message="No upcoming events found" />
          ) : (
            events.slice(0, 8).map((event) => (
              <EventRow key={event.id} event={event} />
            ))
          )}
        </div>
      </div>

      {/* SECTION 3: OPPORTUNITIES - Filtered by Segment Card */}
      <div style={{ marginBottom: '48px' }}>
        <h2 style={{
          fontSize: '12px',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '1px',
          opacity: 0.6,
          marginBottom: '16px'
        }}>
          {activeSegment === 'all' && `ALL ACCOUNTS (${filteredOpportunities.length})`}
          {activeSegment === 'customers' && `CUSTOMERS (${filteredOpportunities.length})`}
          {activeSegment === 'prospects' && `PROSPECTS (${filteredOpportunities.length})`}
          {activeSegment === 'events' && `ALL ACCOUNTS (${filteredOpportunities.length})`}
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {loading ? (
            <LoadingRow />
          ) : filteredOpportunities.length === 0 ? (
            <EmptyRow message="No accounts in this segment" />
          ) : (
            filteredOpportunities.slice(0, 15).map((opp) => (
              <OpportunityRow key={opp.id} opportunity={opp} />
            ))
          )}
        </div>
      </div>

    </div>
  )
}

// =============================================================================
// SEGMENT CARD - Clickable filter with stats
// =============================================================================

function SegmentCard({
  label,
  active,
  onClick,
  color,
  mainValue,
  stats,
}: {
  label: string
  active: boolean
  onClick: () => void
  color: string
  mainValue: number
  stats: { label: string; value: string | number }[]
}) {
  return (
    <button
      onClick={onClick}
      style={{
        background: active ? `${color}15` : 'rgba(255, 255, 255, 0.02)',
        border: active ? `2px solid ${color}` : '1px solid rgba(255, 255, 255, 0.08)',
        borderLeft: `4px solid ${color}`,
        padding: '20px 16px',
        minHeight: '140px',
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        cursor: 'pointer',
        transition: 'all 0.2s ease',
        textAlign: 'left',
      }}
    >
      {/* Top: Main Value + Label */}
      <div>
        <div style={{
          fontSize: '36px',
          fontWeight: 700,
          color: active ? color : 'rgba(255,255,255,0.9)',
          lineHeight: 1,
          marginBottom: '6px',
        }}>
          {mainValue}
        </div>
        <div style={{
          fontSize: '11px',
          fontWeight: 600,
          textTransform: 'uppercase',
          letterSpacing: '0.5px',
          color: active ? color : 'rgba(255,255,255,0.5)',
        }}>
          {label}
        </div>
      </div>

      {/* Bottom: Stats Row */}
      <div style={{
        display: 'flex',
        gap: '16px',
        marginTop: '16px',
        paddingTop: '12px',
        borderTop: '1px solid rgba(255,255,255,0.08)',
      }}>
        {stats.map((stat, idx) => (
          <div key={idx}>
            <div style={{
              fontSize: '14px',
              fontWeight: 600,
              color: 'rgba(255,255,255,0.8)',
            }}>
              {stat.value}
            </div>
            <div style={{
              fontSize: '9px',
              fontWeight: 500,
              textTransform: 'uppercase',
              letterSpacing: '0.5px',
              color: 'rgba(255,255,255,0.4)',
            }}>
              {stat.label}
            </div>
          </div>
        ))}
      </div>
    </button>
  )
}

// =============================================================================
// EVENT ROW - PredictHQ Style
// =============================================================================

function EventRow({ event }: { event: VegasEvent }) {
  // Format date range
  const startDate = new Date(event.startDate)
  const formatDate = (d: Date) => d.toLocaleDateString('en-US', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    year: 'numeric'
  })

  // Calculate duration if we have end date
  const endDate = event.endDate ? new Date(event.endDate) : null
  const duration = endDate
    ? Math.ceil((endDate.getTime() - startDate.getTime()) / (1000 * 60 * 60 * 24)) + 1
    : 1

  return (
    <div style={{
      background: 'rgba(255, 255, 255, 0.02)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      padding: '20px 24px',
      display: 'flex',
      alignItems: 'center',
      gap: '24px',
    }}>
      {/* Left: Event Info */}
      <div style={{ flex: 1, minWidth: 0 }}>
        {/* Event Name */}
        <div style={{
          fontSize: '16px',
          fontWeight: 600,
          color: 'rgba(255,255,255,0.95)',
          marginBottom: '6px',
        }}>
          {event.name}
        </div>

        {/* Location + Category Badge */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          marginBottom: '6px',
        }}>
          <span style={{ fontSize: '13px', color: 'rgba(255,255,255,0.5)' }}>
            {event.venue || 'Las Vegas'}
          </span>
          {event.category && (
            <span style={{
              fontSize: '10px',
              fontWeight: 600,
              textTransform: 'uppercase',
              padding: '2px 8px',
              background: `${event.color}20`,
              color: event.color,
              borderRadius: '2px',
            }}>
              {event.category}
            </span>
          )}
        </div>

        {/* Date Range */}
        <div style={{
          fontSize: '12px',
          color: 'rgba(255,255,255,0.4)',
        }}>
          {formatDate(startDate)}
          {endDate && ` - ${formatDate(endDate)}`}
          {duration > 1 && ` (${duration} days)`}
        </div>
      </div>

      {/* Right: Attendance + Rank/Local circles */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '16px',
        flexShrink: 0,
      }}>
        {/* Predicted Attendance */}
        <div style={{ textAlign: 'right' }}>
          <div style={{
            fontSize: '20px',
            fontWeight: 700,
            color: 'rgba(255,255,255,0.9)',
          }}>
            {event.attendance.toLocaleString()}
          </div>
          <div style={{
            fontSize: '10px',
            color: 'rgba(255,255,255,0.4)',
            textTransform: 'uppercase',
          }}>
            Predicted Attendance
          </div>
        </div>

        {/* Rank Circle */}
        <RankCircle value={event.rank} label="Rank" color="#ec4899" />

        {/* Local Circle */}
        <RankCircle value={event.localRank} label="Local" color="#06b6d4" />
      </div>
    </div>
  )
}

// =============================================================================
// RANK CIRCLE - PredictHQ Style
// =============================================================================

function RankCircle({
  value,
  label,
  color
}: {
  value: number | null
  label: string
  color: string
}) {
  const displayValue = value ?? '-'

  return (
    <div style={{
      width: '52px',
      height: '52px',
      borderRadius: '50%',
      border: `3px solid ${color}`,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      flexShrink: 0,
    }}>
      <div style={{
        fontSize: '16px',
        fontWeight: 700,
        color: 'rgba(255,255,255,0.9)',
        lineHeight: 1,
      }}>
        {displayValue}
      </div>
      <div style={{
        fontSize: '8px',
        color: 'rgba(255,255,255,0.5)',
        textTransform: 'uppercase',
      }}>
        {label}
      </div>
    </div>
  )
}


// =============================================================================
// OPPORTUNITY ROW
// =============================================================================

function OpportunityRow({ opportunity }: { opportunity: Opportunity }) {
  const isProspect = opportunity.status === 'prospect'
  const accentColor = isProspect ? STATUS_COLORS.prospect : STATUS_COLORS.customer

  return (
    <div style={{
      display: 'flex',
      alignItems: 'stretch',
      background: 'rgba(255, 255, 255, 0.02)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
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
        padding: '16px 24px',
        flex: 1,
      }}>
        {/* Main Content */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            marginBottom: '4px'
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
          }}>
            {opportunity.fryer_count} fryers ({opportunity.total_capacity_lbs || 0} lbs) | {opportunity.service_frequency || 'No schedule'}
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
      Loading...
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
