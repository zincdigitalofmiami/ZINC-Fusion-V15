'use client'

import { useEffect, useState } from 'react'

/**
 * Vegas Intel Page - Sales Command Center
 * 
 * Data Source: Glide API → ops.vegas_* tables → /api/vegas
 * Design: TradingView aesthetic - BIG charts, BIG cards, breathing room
 */

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
  status?: string
  message?: string
}

interface Restaurant {
  id: number
  name: string
  location: string
  category: string
  current_oil_lbs: number | null
  delivery_day: string
  fryers: number | null
  data: Record<string, unknown>
}

interface Casino {
  id: number
  name: string
  event_calendar: string
  premium_tier: boolean
  data: Record<string, unknown>
}

// =============================================================================
// Main Component
// =============================================================================

export default function VegasIntelPage() {
  const [stats, setStats] = useState<VegasStats | null>(null)
  const [restaurants, setRestaurants] = useState<Restaurant[]>([])
  const [casinos, setCasinos] = useState<Casino[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

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

        // Fetch casinos
        const casinoRes = await fetch('/api/vegas?view=casinos')
        const casinoData = await casinoRes.json()
        setCasinos(casinoData.casinos || [])

      } catch (err) {
        setError(String(err))
      } finally {
        setLoading(false)
      }
    }

    fetchData()
  }, [])

  // Not synced state
  const notSynced = stats?.status === 'not_synced' || stats?.total_customers === 0

  return (
    <div className="main-content" style={{ maxWidth: '1800px' }}>
      {/* Page Header */}
      <div className="page-header" style={{ marginBottom: '48px' }}>
        <h1 className="page-title" style={{ fontSize: '36px' }}>Vegas Intel</h1>
        <p className="page-subtitle" style={{ fontSize: '18px', opacity: 0.7 }}>
          Sales command center — Real customer data from US Oil Solutions Glide
        </p>
        {stats?.last_sync && (
          <p style={{ fontSize: '12px', opacity: 0.5, marginTop: '8px' }}>
            Last sync: {new Date(stats.last_sync).toLocaleString()}
          </p>
        )}
      </div>

      {/* Data Not Synced Alert */}
      {notSynced && (
        <div className="alert-banner" style={{ marginBottom: '40px', padding: '24px' }}>
          <div style={{ fontSize: '14px' }}>
            <strong>Data Not Synced</strong> — Run the Glide ingestion script to populate Vegas customer data:
          </div>
          <code style={{ 
            display: 'block', 
            marginTop: '12px', 
            padding: '12px', 
            background: 'rgba(0,0,0,0.3)', 
            borderRadius: '8px',
            fontFamily: 'monospace'
          }}>
            cd /Volumes/Satechi\ Hub/ZINC-FUSION-V15 && python -m fusion.ingestion.glide_vegas
          </code>
        </div>
      )}

      {/* BIG Stats Cards - TradingView Style */}
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(4, 1fr)', 
        gap: '32px', 
        marginBottom: '60px' 
      }}>
        <StatCard 
          value={stats?.restaurants || 0} 
          label="Restaurants" 
          color="#2962FF" 
          loading={loading}
        />
        <StatCard 
          value={stats?.casinos || 0} 
          label="Casinos" 
          color="#81c784" 
          loading={loading}
        />
        <StatCard 
          value={stats?.fryers || 0} 
          label="Fryers" 
          color="#ffb464" 
          loading={loading}
        />
        <StatCard 
          value={stats?.export_list || 0} 
          label="Customer Records" 
          color="#ef5350" 
          loading={loading}
        />
      </div>

      {/* Two Column Layout */}
      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: '40px' }}>
        
        {/* Left: Customer List (BIG CARD) */}
        <div className="card-elevated" style={{ padding: '32px' }}>
          <div style={{ 
            display: 'flex', 
            justifyContent: 'space-between', 
            alignItems: 'center', 
            marginBottom: '32px' 
          }}>
            <h2 style={{ fontSize: '20px', fontWeight: 600 }}>Restaurant Customers</h2>
            <span style={{ fontSize: '14px', opacity: 0.5 }}>
              {restaurants.length} accounts
            </span>
          </div>

          {loading ? (
            <LoadingState />
          ) : restaurants.length === 0 ? (
            <EmptyState message="No restaurant data synced yet" />
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {restaurants.slice(0, 10).map((r) => (
                <RestaurantCard key={r.id} restaurant={r} />
              ))}
              {restaurants.length > 10 && (
                <div style={{ 
                  textAlign: 'center', 
                  padding: '16px', 
                  opacity: 0.5 
                }}>
                  + {restaurants.length - 10} more restaurants
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right: Casinos & Quick Info */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '32px' }}>
          
          {/* Casino Partners */}
          <div className="card-elevated" style={{ padding: '28px' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '24px' }}>
              Casino Partners
            </h2>
            {loading ? (
              <LoadingState />
            ) : casinos.length === 0 ? (
              <EmptyState message="No casino data synced yet" />
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                {casinos.slice(0, 8).map((c) => (
                  <CasinoCard key={c.id} casino={c} />
                ))}
              </div>
            )}
          </div>

          {/* Market Talking Points */}
          <div className="card" style={{ padding: '28px' }}>
            <h2 style={{ fontSize: '18px', fontWeight: 600, marginBottom: '24px' }}>
              Sales Talking Points
            </h2>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <TalkingPoint 
                type="bullish" 
                title="BULLISH POINT"
                text="EPA RVO rule expected to boost biodiesel demand 15%. Lock in supply now before Q1 price surge."
              />
              <TalkingPoint 
                type="urgency"
                title="URGENCY DRIVER" 
                text="Trump tariff threats creating uncertainty. Secure contracts before potential trade disruption."
              />
              <TalkingPoint 
                type="value"
                title="VALUE PROP" 
                text="Our AI forecasts show 87% confidence in near-term price support. Ideal timing for annual contracts."
              />
            </div>
          </div>

          {/* Sync Status */}
          <div className="card" style={{ padding: '24px' }}>
            <h3 style={{ fontSize: '14px', fontWeight: 600, marginBottom: '16px', opacity: 0.8 }}>
              Data Sources
            </h3>
            <div style={{ fontSize: '12px', lineHeight: 2 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ opacity: 0.6 }}>Restaurants</span>
                <span style={{ color: stats?.restaurants ? '#81c784' : '#ef5350' }}>
                  {stats?.restaurants || 0} rows
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ opacity: 0.6 }}>Casinos</span>
                <span style={{ color: stats?.casinos ? '#81c784' : '#ef5350' }}>
                  {stats?.casinos || 0} rows
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ opacity: 0.6 }}>Fryers</span>
                <span style={{ color: stats?.fryers ? '#81c784' : '#ef5350' }}>
                  {stats?.fryers || 0} rows
                </span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ opacity: 0.6 }}>Export List</span>
                <span style={{ color: stats?.export_list ? '#81c784' : '#ef5350' }}>
                  {stats?.export_list || 0} rows
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {error && (
        <div style={{ 
          marginTop: '40px', 
          padding: '20px', 
          background: 'rgba(239, 83, 80, 0.1)', 
          border: '1px solid rgba(239, 83, 80, 0.3)',
          borderRadius: '12px',
          color: '#ef5350'
        }}>
          Error: {error}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// Sub-Components
// =============================================================================

function StatCard({ value, label, color, loading }: { 
  value: number
  label: string
  color: string
  loading: boolean 
}) {
  return (
    <div className="card-elevated" style={{ 
      padding: '40px', 
      textAlign: 'center',
      borderLeft: `4px solid ${color}`
    }}>
      <div style={{ 
        fontSize: '56px', 
        fontWeight: 700, 
        color,
        lineHeight: 1,
        marginBottom: '16px'
      }}>
        {loading ? '—' : value.toLocaleString()}
      </div>
      <div style={{ fontSize: '14px', opacity: 0.6, textTransform: 'uppercase', letterSpacing: '1px' }}>
        {label}
      </div>
    </div>
  )
}

function RestaurantCard({ restaurant }: { restaurant: Restaurant }) {
  const initials = restaurant.name.split(' ').map(w => w[0]).join('').slice(0, 2).toUpperCase()
  
  return (
    <div style={{ 
      display: 'flex', 
      gap: '20px', 
      padding: '20px', 
      background: 'rgba(255, 255, 255, 0.02)', 
      border: '1px solid rgba(255, 255, 255, 0.08)', 
      borderRadius: '12px',
      transition: 'all 0.2s ease'
    }}>
      <div style={{ 
        width: '52px', 
        height: '52px', 
        borderRadius: '12px', 
        background: 'rgba(41, 98, 255, 0.15)', 
        display: 'flex', 
        alignItems: 'center', 
        justifyContent: 'center', 
        fontWeight: 700, 
        fontSize: '18px',
        color: '#2962FF',
        flexShrink: 0
      }}>
        {initials}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 600, fontSize: '15px', marginBottom: '6px' }}>
          {restaurant.name}
        </div>
        <div style={{ fontSize: '13px', opacity: 0.6 }}>
          {restaurant.location} • {restaurant.category}
        </div>
        {restaurant.delivery_day && (
          <div style={{ fontSize: '12px', opacity: 0.5, marginTop: '4px' }}>
            Delivery: {restaurant.delivery_day}
          </div>
        )}
      </div>
      <div style={{ textAlign: 'right', flexShrink: 0 }}>
        {restaurant.fryers && (
          <div style={{ fontSize: '12px', opacity: 0.5 }}>
            {restaurant.fryers} fryer{restaurant.fryers > 1 ? 's' : ''}
          </div>
        )}
        {restaurant.current_oil_lbs && (
          <div style={{ fontWeight: 600, color: '#81c784', fontSize: '14px' }}>
            {restaurant.current_oil_lbs.toLocaleString()} lbs
          </div>
        )}
      </div>
    </div>
  )
}

function CasinoCard({ casino }: { casino: Casino }) {
  return (
    <div style={{ 
      display: 'flex', 
      justifyContent: 'space-between', 
      alignItems: 'center',
      padding: '16px', 
      background: 'rgba(255, 255, 255, 0.02)', 
      borderRadius: '10px'
    }}>
      <div>
        <div style={{ fontWeight: 600, marginBottom: '4px' }}>{casino.name}</div>
        {casino.event_calendar && (
          <div style={{ fontSize: '11px', opacity: 0.5 }}>{casino.event_calendar}</div>
        )}
      </div>
      {casino.premium_tier && (
        <span style={{ 
          padding: '4px 10px', 
          background: 'rgba(255, 180, 100, 0.2)', 
          borderRadius: '4px', 
          fontSize: '10px', 
          fontWeight: 600, 
          color: '#ffb464',
          textTransform: 'uppercase'
        }}>
          Premium
        </span>
      )}
    </div>
  )
}

function TalkingPoint({ type, title, text }: { type: string; title: string; text: string }) {
  const colors: Record<string, { bg: string; text: string }> = {
    bullish: { bg: 'rgba(41, 98, 255, 0.1)', text: '#2962FF' },
    urgency: { bg: 'rgba(255, 180, 100, 0.1)', text: '#ffb464' },
    value: { bg: 'rgba(255, 255, 255, 0.05)', text: 'rgba(255,255,255,0.8)' }
  }
  const c = colors[type] || colors.value

  return (
    <div style={{ padding: '16px', background: c.bg, borderRadius: '10px' }}>
      <div style={{ fontSize: '11px', fontWeight: 600, color: c.text, marginBottom: '10px' }}>
        {title}
      </div>
      <div style={{ fontSize: '14px', lineHeight: 1.6 }}>
        &ldquo;{text}&rdquo;
      </div>
    </div>
  )
}

function LoadingState() {
  return (
    <div style={{ padding: '40px', textAlign: 'center', opacity: 0.5 }}>
      Loading data...
    </div>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <div style={{ 
      padding: '60px 40px', 
      textAlign: 'center', 
      opacity: 0.5,
      background: 'rgba(255,255,255,0.02)',
      borderRadius: '12px'
    }}>
      {message}
    </div>
  )
}
