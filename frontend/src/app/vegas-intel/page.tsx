'use client'

import { useEffect, useState } from 'react'

/**
 * Vegas Intel Page - Kevin's Sales Command Center
 * 
 * SPEC: /Docs/VEGAS_INTEL_SPEC_LOCKED.md
 * 
 * Layout:
 * 1. Event Cards (horizontal row, same slice as stat cards)
 * 2. Opportunities (full-width rows, existing customers + prospects)
 * 3. At Risk (full-width rows, churn alerts)
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
  name: string
  location: string
  category: string
  fryers: number | null
  delivery_day: string
  data: Record<string, unknown>
}

// Placeholder until we build the event system
interface VegasEvent {
  id: string
  name: string
  attendance: number
  startDate: string
  endDate: string
  daysUntil: number
  color: string
}

// Placeholder until we build the model
interface Opportunity {
  id: number
  name: string
  casino: string
  status: 'customer' | 'prospect'
  eventMatch: 'HIGH' | 'MEDIUM' | 'LOW'
  projectedMin: number
  projectedMax: number
  fryers: number | null
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
// Status Colors (soft, not harsh)
// =============================================================================

const STATUS_COLORS = {
  customer: '#4ade80',  // soft green
  prospect: '#b91c1c',  // maroon
  atRisk: '#fbbf24',    // amber
}

// =============================================================================
// Mock Data (will be replaced with API calls)
// =============================================================================

const MOCK_EVENTS: VegasEvent[] = [
  { id: '1', name: 'CES 2026', attendance: 180000, startDate: '2026-01-07', endDate: '2026-01-10', daysUntil: 10, color: '#2962FF' },
  { id: '2', name: 'UFC 312', attendance: 22000, startDate: '2026-01-18', endDate: '2026-01-18', daysUntil: 18, color: '#4ade80' },
  { id: '3', name: 'F1 VEGAS', attendance: 315000, startDate: '2026-03-15', endDate: '2026-03-17', daysUntil: 60, color: '#ffb464' },
  { id: '4', name: 'MAGIC CON', attendance: 45000, startDate: '2026-02-24', endDate: '2026-02-27', daysUntil: 41, color: '#ef5350' },
]

// =============================================================================
// Main Component
// =============================================================================

export default function VegasIntelPage() {
  const [stats, setStats] = useState<VegasStats | null>(null)
  const [restaurants, setRestaurants] = useState<Restaurant[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedEvent, setSelectedEvent] = useState<string | null>('1') // CES selected by default
  const [filter, setFilter] = useState<'all' | 'customers' | 'prospects'>('all')

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
    fetchData()
  }, [])

  // Transform restaurants into opportunities (placeholder logic)
  const opportunities: Opportunity[] = restaurants.slice(0, 8).map((r, i) => ({
    id: r.id,
    name: r.name,
    casino: r.location || 'Las Vegas',
    status: i < 6 ? 'customer' : 'prospect',
    eventMatch: i < 3 ? 'HIGH' : i < 6 ? 'MEDIUM' : 'HIGH',
    projectedMin: 20 + (i * 5),
    projectedMax: 35 + (i * 5),
    fryers: r.fryers,
    oneLiner: i < 6 
      ? "Prime corridor. Event crowd is their demo."
      : "You don't have them. Money on the table.",
  }))

  // Mock at-risk data (placeholder)
  const atRiskCustomers: AtRiskCustomer[] = [
    { id: 999, name: 'Wynn Buffet', casino: 'Wynn', daysSinceOrder: 18, pattern: 'weekly → silent', oneLiner: "Something's wrong. Call today." },
    { id: 998, name: 'Aria Café', casino: 'Aria', daysSinceOrder: 14, pattern: 'bi-weekly → silent', oneLiner: "They went quiet. Find out why." },
  ]

  // Filter opportunities
  const filteredOpportunities = opportunities.filter(o => {
    if (filter === 'all') return true
    if (filter === 'customers') return o.status === 'customer'
    if (filter === 'prospects') return o.status === 'prospect'
    return true
  })

  const selectedEventData = MOCK_EVENTS.find(e => e.id === selectedEvent)
  const headline = selectedEventData 
    ? `${selectedEventData.name} is ${selectedEventData.daysUntil} days out. ${selectedEventData.attendance.toLocaleString()} people. Here's your play.`
    : "Select an event to see your opportunities."

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
      </div>

      {/* ================================================================
          SECTION 1: EVENT CARDS (Same slice as stat cards)
          ================================================================ */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(4, 1fr)', 
        gap: '24px', 
        marginBottom: '48px' 
      }}>
        {MOCK_EVENTS.map((event) => (
          <EventCard 
            key={event.id} 
            event={event} 
            selected={selectedEvent === event.id}
            onClick={() => setSelectedEvent(event.id)}
          />
        ))}
      </div>

      {/* ================================================================
          SECTION 2: OPPORTUNITIES
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
            OPPORTUNITIES
          </h2>
          <FilterToggle value={filter} onChange={setFilter} />
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {loading ? (
            <LoadingRow />
          ) : filteredOpportunities.length === 0 ? (
            <EmptyRow message="No opportunities match your filter" />
          ) : (
            filteredOpportunities.map((opp) => (
              <OpportunityRow key={opp.id} opportunity={opp} />
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
          AT RISK
        </h2>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          {atRiskCustomers.map((customer) => (
            <AtRiskRow key={customer.id} customer={customer} />
          ))}
        </div>
      </div>

    </div>
  )
}

// =============================================================================
// EVENT CARD (Same slice as stat cards - colored left border)
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
        borderRadius: '0px', // squared
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
// OPPORTUNITY ROW (Full width, squared, clean)
// =============================================================================

function OpportunityRow({ opportunity }: { opportunity: Opportunity }) {
  const isProspect = opportunity.status === 'prospect'
  const accentColor = isProspect ? STATUS_COLORS.prospect : '#2dd4bf' // teal for customers

  return (
    <div style={{ 
      display: 'flex',
      alignItems: 'stretch',
      background: 'rgba(255, 255, 255, 0.02)',
      border: '1px solid rgba(255, 255, 255, 0.08)',
      borderRadius: '0px', // squared
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
          CES match: {opportunity.eventMatch} │ Projected: +{opportunity.projectedMin}-{opportunity.projectedMax}% │ {opportunity.fryers || '?'} fryers
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
      borderRadius: '0px', // squared
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
            {customer.daysSinceOrder} DAYS
          </span>
        </div>
        <div style={{ 
          fontSize: '12px', 
          opacity: 0.5,
          marginBottom: '8px'
        }}>
          Last order: {customer.daysSinceOrder} days ago │ Pattern: {customer.pattern}
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
