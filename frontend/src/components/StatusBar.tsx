'use client'

import { useEffect, useState } from 'react'

interface StatusBarProps {
  zlPrice?: number
  zlChange?: number
  zlChangePercent?: number
  regime?: 'stable' | 'rising' | 'falling' | 'volatile' | 'crisis'
  confidence?: number
  lastUpdate?: Date
  isStale?: boolean
}

export default function StatusBar({
  zlPrice = 42.85,
  zlChange = -0.47,
  zlChangePercent = -1.08,
  regime = 'volatile',
  confidence = 87,
  lastUpdate = new Date(),
  isStale = false,
}: StatusBarProps) {
  const [displayTime, setDisplayTime] = useState<string>('')

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
