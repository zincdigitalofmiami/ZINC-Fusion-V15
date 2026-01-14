'use client'

import React from 'react'

// Chris's TOP 4 Key Drivers - The metrics he originally wanted
// These represent the 4 core market pressures he monitors

interface DriverGaugeProps {
  label: string
  value: number
  subLabel: string
  subValue: string
  weight: number
  variant?: 'stress' | 'supply' | 'tension' | 'threat'
}

// Arc gauge colors
const VARIANTS = {
  stress: { stroke: '#EF4444', bg: 'rgba(239, 68, 68, 0.1)' },   // Red
  supply: { stroke: '#22C55E', bg: 'rgba(34, 197, 94, 0.1)' },   // Green
  tension: { stroke: '#F59E0B', bg: 'rgba(245, 158, 11, 0.1)' }, // Amber
  threat: { stroke: '#00D4FF', bg: 'rgba(0, 212, 255, 0.1)' },   // Cyan
}

function ArcGauge({ value, variant = 'stress' }: { value: number; variant: DriverGaugeProps['variant'] }) {
  // Value should be 0-2 range (or normalized)
  const normalizedValue = Math.min(Math.max(value, 0), 2)
  const percentage = (normalizedValue / 2) * 100
  
  // Arc parameters
  const radius = 40
  const strokeWidth = 3 // THIN crisp line
  const circumference = Math.PI * radius // Half circle
  const strokeDasharray = circumference
  const strokeDashoffset = circumference - (circumference * percentage / 100)
  
  const colors = VARIANTS[variant || 'stress']
  
  return (
    <svg viewBox="0 0 100 55" className="w-full h-auto">
      {/* Background arc */}
      <path
        d="M 10 50 A 40 40 0 0 1 90 50"
        fill="none"
        stroke="rgba(255, 255, 255, 0.05)"
        strokeWidth={strokeWidth}
        strokeLinecap="round"
      />
      {/* Value arc */}
      <path
        d="M 10 50 A 40 40 0 0 1 90 50"
        fill="none"
        stroke={colors.stroke}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={strokeDasharray}
        strokeDashoffset={strokeDashoffset}
        style={{ 
          transition: 'stroke-dashoffset 0.8s ease-out',
          filter: `drop-shadow(0 0 6px ${colors.stroke}40)` 
        }}
      />
    </svg>
  )
}

function DriverGaugeCard({ label, value, subLabel, subValue, weight, variant = 'stress' }: DriverGaugeProps) {
  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-5 flex flex-col items-center hover:border-white/10 transition-colors">
      {/* Label */}
      <div className="text-[10px] font-bold text-slate-400 uppercase tracking-[0.2em] mb-2">
        {label}
      </div>
      
      {/* Arc Gauge */}
      <div className="w-28 -mb-3">
        <ArcGauge value={value} variant={variant} />
      </div>
      
      {/* Main Value */}
      <div className="text-3xl font-bold text-white tabular-nums -mt-1">
        {value.toFixed(2)}
      </div>
      
      {/* Sub metrics */}
      <div className="text-[10px] text-slate-500 mt-2 space-y-0.5 text-center">
        <div>{subLabel}: {subValue}</div>
        <div className="text-slate-600">Weight: {weight}%</div>
      </div>
    </div>
  )
}

interface ChrisTop4Data {
  vixStress: { value: number; current: number; normal: number }
  harvestPace: { value: number; combined: string }
  chinaTension: { value: number; relations: string }
  tariffThreat: { value: number; mentions: string; risk: string }
}

export function ChrisTop4Drivers({ 
  data 
}: { 
  data?: ChrisTop4Data 
}) {
  // Default data (will be replaced with real API data)
  const defaultData: ChrisTop4Data = {
    vixStress: { value: 1.85, current: 31.2, normal: 20.0 },
    harvestPace: { value: 0.76, combined: '76% of Normal' },
    chinaTension: { value: 0.74, relations: 'High Tension' },
    tariffThreat: { value: 0.89, mentions: '7-Day', risk: 'Elevated Risk' },
  }
  
  const d = data || defaultData

  return (
    <div className="w-full">
      {/* Section Header */}
      <div className="flex items-center gap-2 mb-4 pl-1 border-l-4 border-cyan-500">
        <h3 className="text-sm font-bold text-white uppercase tracking-wider">
          Key Market Drivers
        </h3>
        <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
          CHRIS'S TOP 4
        </span>
      </div>
      
      {/* 4 Gauge Grid */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <DriverGaugeCard
          label="VIX Stress"
          value={d.vixStress.value}
          subLabel="Current"
          subValue={d.vixStress.current.toFixed(1)}
          weight={68}
          variant="stress"
        />
        <DriverGaugeCard
          label="Harvest Pace"
          value={d.harvestPace.value}
          subLabel="SA Combined"
          subValue={d.harvestPace.combined}
          weight={45}
          variant="supply"
        />
        <DriverGaugeCard
          label="China Tension"
          value={d.chinaTension.value}
          subLabel="Trade Relations"
          subValue={d.chinaTension.relations}
          weight={15}
          variant="tension"
        />
        <DriverGaugeCard
          label="Tariff Threat"
          value={d.tariffThreat.value}
          subLabel={d.tariffThreat.mentions}
          subValue={d.tariffThreat.risk}
          weight={70}
          variant="threat"
        />
      </div>
    </div>
  )
}

// Compact version for sidebar/secondary placement
export function ChrisTop4Compact() {
  const drivers = [
    { label: 'VIX', value: 1.85, color: '#EF4444' },
    { label: 'Harvest', value: 0.76, color: '#22C55E' },
    { label: 'China', value: 0.74, color: '#F59E0B' },
    { label: 'Tariff', value: 0.89, color: '#00D4FF' },
  ]

  return (
    <div className="flex items-center gap-4">
      {drivers.map((d) => (
        <div key={d.label} className="flex items-center gap-1.5">
          <div 
            className="w-1.5 h-1.5 rounded-full"
            style={{ backgroundColor: d.color }}
          />
          <span className="text-[10px] text-slate-500 uppercase">{d.label}</span>
          <span className="text-xs font-mono text-white">{d.value.toFixed(2)}</span>
        </div>
      ))}
    </div>
  )
}
