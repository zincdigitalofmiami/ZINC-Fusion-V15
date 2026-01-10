'use client'

import { useEffect, useState } from 'react'

interface ZlLiveData {
  price: number
  change: number
  change_pct: number
  updated_at: string
}

interface StatusBarProps {
  regime?: 'stable' | 'rising' | 'falling' | 'volatile' | 'crisis'
  confidence?: number
}

export default function StatusBar({
  regime = 'volatile',
  confidence = 87,
}: StatusBarProps) {
  const [displayTime, setDisplayTime] = useState<string>('')
  const [zlData, setZlData] = useState<ZlLiveData | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [isStale, setIsStale] = useState(false)

  // Fetch live ZL price
  useEffect(() => {
    async function fetchZlLive() {
      try {
        const res = await fetch('/api/zl/live')
        if (!res.ok) throw new Error('Failed to fetch ZL live')
        const json = await res.json()
        setZlData({
          price: json.price,
          change: json.change,
          change_pct: json.change_pct,
          updated_at: json.updated_at
        })
        
        // Check if data is stale (>30 min old)
        const updatedAt = new Date(json.updated_at)
        const now = new Date()
        setIsStale((now.getTime() - updatedAt.getTime()) > 30 * 60 * 1000)
        setError(null)
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Unknown error')
      } finally {
        setLoading(false)
      }
    }
    fetchZlLive()
    // Refresh every 60 seconds
    const interval = setInterval(fetchZlLive, 60000)
    return () => clearInterval(interval)
  }, [])

  useEffect(() => {
    const formatTime = () => {
      const now = new Date()
      return now.toLocaleTimeString('en-US', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
      })
    }
    setDisplayTime(formatTime())
    const interval = setInterval(() => setDisplayTime(formatTime()), 1000)
    return () => clearInterval(interval)
  }, [])

  const zlPrice = zlData?.price ?? 0
  const zlChange = zlData?.change ?? 0
  const zlChangePercent = zlData?.change_pct ?? 0
  const isPositive = zlChange >= 0
  const priceChangeClass = isPositive ? 'positive' : 'negative'

  const regimeLabels: Record<string, string> = {
    stable: 'Stable',
    rising: 'Rising',
    falling: 'Falling',
    volatile: 'Volatile',
    crisis: 'Crisis',
  }

  const confidenceClass = confidence >= 80 ? 'high' : ''

  return (
    <div className="status-bar">
      <div className="status-left">
        <div className="zl-price">
          ZL: ${zlPrice.toFixed(2)}
          <span className={`price-delta ${priceChangeClass}`}>
            {' '}
            {isPositive ? '+' : ''}
            {zlChange.toFixed(2)} ({isPositive ? '+' : ''}
            {zlChangePercent.toFixed(2)}%)
          </span>
        </div>
        <div className={`regime-chip ${regime}`}>{regimeLabels[regime]}</div>
        <div className={`confidence-badge ${confidenceClass}`}>{confidence}% Conf</div>
      </div>
      <div className="status-right">
        {isStale && <div className="stale-banner">Stale Data</div>}
        <div className="last-update">{displayTime}</div>
        <div className="fast-actions">
          <button className="action-btn">↻</button>
          <button className="action-btn">⚙</button>
        </div>
      </div>
    </div>
  )
}
