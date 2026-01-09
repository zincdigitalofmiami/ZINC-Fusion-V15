# Strategy Command Dashboard Prototype
**Date:** January 9, 2026
**Version:** v1.0 (Prototype)

This document captures the current state of the "Strategy Command" dashboard design, including the main layout, the L0-L3 Fusion Chart (with watermark logic), and the Quant Admin Sidebar.

## 1. Main Dashboard Layout (`start/src/app/dashboard/page.tsx`)

This is the composition layer that arranges the chart, signal gauges, and tool widgets.

```tsx
'use client';

import React, { useState } from 'react';
import ZLPriceChart from '@/components/ZLPriceChart';
import { SignalGauge } from '@/components/ui/SignalGauge';
import { ContractImpactCalculator } from '@/components/tools/ContractImpactCalculator';
import { MarketCommentary } from '@/components/ui/MarketCommentary';
import { FactorWaterfall } from '@/components/quant/FactorWaterfall';
import { ProbabilityHeatmap } from '@/components/quant/ProbabilityHeatmap';
import { FusionBrain } from '@/components/viz/FusionBrain';
import { WeatherRiskArray } from '@/components/viz/WeatherRiskArray';
import { QuantAdminSidebar } from '@/components/layout/QuantAdminSidebar';
import { BrainCircuit, Wind, TrendingUp, AlertTriangle, Menu, Activity } from 'lucide-react';

export default function DashboardPage() {
  const [isAdminOpen, setIsAdminOpen] = useState(false);

  return (
    <div className="min-h-screen animate-in fade-in duration-500 p-6 space-y-8 pb-20 bg-[#0a0a0a]">
      
      <QuantAdminSidebar isOpen={isAdminOpen} onClose={() => setIsAdminOpen(false)} />

      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/5 pb-6">
        <div>
          <h1 className="text-3xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-white to-slate-400">
            STRATEGY COMMAND
          </h1>
          <p className="text-slate-400 mt-1 font-mono text-sm tracking-wide">
             ALTERNATIVE DATA INTELLIGENCE // MULTI-HORIZON XAI
          </p>
        </div>
        <div className="flex items-center gap-6">
            <div className="flex items-center gap-4 text-xs font-mono text-slate-500">
            <div className="flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                LIVE FEED
            </div>
            <div>UPDATED: 14:02 CST</div>
            </div>
            
            <button 
                onClick={() => setIsAdminOpen(true)}
                className="p-2 hover:bg-white/10 rounded-md text-slate-400 hover:text-white transition-colors border border-transparent hover:border-white/10"
            >
                <Menu size={20} />
            </button>
        </div>
      </div>

      {/* SECTION 1: THE MASSIVE CHART (L0-L3 FUSION) */}
      <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-1 shadow-2xl shadow-black/50 relative">
          <div className="absolute top-4 left-6 z-10 pointer-events-none">
             <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Activity size={18} className="text-emerald-400" />
                ZL CORE FORECAST <span className="text-slate-500 text-sm font-normal">// L3 ENSEMBLE PATH</span>
             </h2>
          </div>
          <ZLPriceChart height={500} />
      </div>

      {/* SECTION 1.5: HORIZON SIGNALS (Moved Up) */}
      <div>
        <div className="flex items-center gap-2 mb-4 pl-1 border-l-4 border-blue-500">
            <h3 className="text-xl font-bold text-white">
                Multi-Horizon Signals
            </h3>
            <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
                ACTIVE
            </span>
        </div>
        
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
            <SignalGauge 
                horizon="1 Week" 
                value={65} 
                trend="bullish" 
                p10={46.20} 
                p90={48.90} 
                confidence="High"
            />
            <SignalGauge 
                horizon="1 Month" 
                value={45} 
                trend="neutral" 
                p10={44.50} 
                p90={50.10} 
                confidence="Med"
            />
            <SignalGauge 
                horizon="3 Months" 
                value={30} 
                trend="bearish" 
                p10={40.20} 
                p90={49.50} 
                confidence="Low"
            />
            <SignalGauge 
                horizon="6 Months" 
                value={25} 
                trend="bearish" 
                p10={38.10} 
                p90={47.80} 
                confidence="Low"
            />
        </div>
      </div>

      {/* SECTION 2: QUANT OPERATIONAL LAYER */}
      <div className="grid grid-cols-12 gap-6">
        
        {/* Left Column: Tools & Drivers (8) */}
        <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
            
            {/* Impact & Waterfall Row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                <ContractImpactCalculator />
                <FactorWaterfall prevPrice={49.20} currentPrice={49.65} />
            </div>

            {/* Heatmap */}
            <ProbabilityHeatmap />

            {/* Brain (Force Graph) */}
            <div className="h-[400px] border border-white/5 rounded-xl overflow-hidden bg-black/20">
                 <div className="p-4 border-b border-white/5 bg-white/5 flex items-center justify-between">
                    <span className="text-xs font-mono text-slate-400 uppercase tracking-widest">Global Causal Network</span>
                    <BrainCircuit size={14} className="text-purple-400" />
                 </div>
                 <FusionBrain />
            </div>
        </div>

        {/* Right Column: Commentary & Risks (4) */}
        <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
            
            {/* Weather Risk Array (New Hi-Def Component) */}
            <WeatherRiskArray />

            {/* Quick Stats / Active Risks */}
            <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6">
                <h3 className="text-sm font-semibold text-white mb-4 uppercase tracking-wider flex items-center gap-2">
                    <AlertTriangle size={16} className="text-amber-400" />
                    Active Risks
                </h3>
                <div className="space-y-3">
                    <div className="p-3 bg-amber-500/10 border border-amber-500/20 rounded-lg">
                        <div className="flex justify-between items-center mb-1">
                            <span className="text-amber-400 text-xs font-bold">TRUMP TARIFFS</span>
                            <span className="text-amber-400 text-xs">HIGH PROB</span>
                        </div>
                        <p className="text-slate-400 text-xs">EPU index &gt; 175. China retaliation likely.</p>
                    </div>
                    <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-lg">
                        <div className="flex justify-between items-center mb-1">
                            <span className="text-blue-400 text-xs font-bold">BIOFUEL MANDATE</span>
                            <span className="text-blue-400 text-xs">MED IMPACT</span>
                        </div>
                        <p className="text-slate-400 text-xs">EPA waiver discussions in progress.</p>
                    </div>
                </div>
            </div>

            {/* Market Commentary */}
            <MarketCommentary />
        </div>

      </div>
      
    </div>
  );
}
```

## 2. ZL Price Chart with Responsive Watermark (`frontend/src/components/ZLPriceChart.tsx`)

This component handles the Plotly visualization, including dynamic model switching and a watermark that adjusts padding based on screen width/mobile state.

```tsx
'use client'

import dynamic from 'next/dynamic'
import { useMemo, useState, useEffect } from 'react'

// Dynamic import to avoid SSR issues with Plotly
const Plot = dynamic(() => import('react-plotly.js'), { 
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[500px] text-slate-500 animate-pulse">
      Initialising L1 Prediction Engine...
    </div>
  )
})

const AVAILABLE_MODELS = [
  { id: 'l1_ensemble', label: 'L1 Ensemble (Meta-Learner)', color: '#00E676' },
  { id: 'core_chronos2', label: 'Core Chronos2 (Foundation)', color: '#2979FF' },
  { id: 'core_deepar', label: 'Core DeepAR (Probabilistic)', color: '#FF9100' },
  { id: 'core_tide', label: 'Core TiDE (Transformer)', color: '#F50057' },
]

interface ZLPriceChartProps {
  height?: number
  data?: {
    dates: string[]
    prices: number[]
    p10?: number[]
    p25?: number[]
    p50?: number[]
    p75?: number[]
    p90?: number[]
  }
}

export default function ZLPriceChart({ height = 500, data }: ZLPriceChartProps) {
  const [selectedModel, setSelectedModel] = useState(AVAILABLE_MODELS[0])
  const [isMobile, setIsMobile] = useState(false)

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth < 768)
    }
    
    // Check initial
    checkMobile()
    
    // Add listener
    window.addEventListener('resize', checkMobile)
    return () => window.removeEventListener('resize', checkMobile)
  }, [])

  // Sample data if none provided
  const chartData = useMemo(() => {
    if (data) return data
    
    // Generate sophisticated looking curve
    const historyDates = []
    const historyPrices = []
    let price = 48.50
    const now = new Date()
    
    // 60 days history
    for(let i=60; i>0; i--) {
        const d = new Date(now)
        d.setDate(d.getDate() - i)
        historyDates.push(d.toISOString().split('T')[0])
        price = price + (Math.random() - 0.48) * 0.8 // slight uptrend bias
        historyPrices.push(price)
    }

    const lastPrice = historyPrices[historyPrices.length-1]
    const forecastDates = []
    const p50 = []
    const p10 = []
    const p25 = []
    const p75 = []
    const p90 = []

    let currentP50 = lastPrice
    
    // 30 days forecast
    for(let i=0; i<30; i++) {
        const d = new Date(now)
        d.setDate(d.getDate() + i)
        forecastDates.push(d.toISOString().split('T')[0])
        
        // Logarithmic decay of certainty + trend
        const dayFactor = Math.sqrt(i + 1) * 0.15
        
        // Slightly different curve shape per model to show "live" switching
        let noise = 0
        if (selectedModel.id === 'core_chronos2') noise = Math.sin(i/2) * 0.1
        if (selectedModel.id === 'core_deepar') noise = Math.cos(i/3) * 0.15
        if (selectedModel.id === 'core_tide') noise = (Math.random() - 0.5) * 0.2

        currentP50 = currentP50 + (0.05 * Math.sin(i/3)) + 0.02 + noise
        
        p50.push(currentP50)
        p25.push(currentP50 - (dayFactor * 0.8))
        p75.push(currentP50 + (dayFactor * 0.8))
        p10.push(currentP50 - (dayFactor * 1.5))
        p90.push(currentP50 + (dayFactor * 1.5))
    }

    return {
      historyDates,
      historyPrices,
      forecastDates,
      p10, p25, p50, p75, p90
    }
  }, [data, selectedModel])

  return (
    <div className="relative group">
      {/* Model Selector Overlay */}
      <div className="absolute top-4 left-16 z-10 flex gap-2">
        <select 
          value={selectedModel.id}
          onChange={(e) => setSelectedModel(AVAILABLE_MODELS.find(m => m.id === e.target.value) || AVAILABLE_MODELS[0])}
          className="bg-black/40 backdrop-blur-md border border-white/10 text-xs text-white rounded px-2 py-1 outline-none hover:bg-black/60 transition-colors cursor-pointer appearance-none pl-3 pr-8"
          style={{ backgroundImage: `url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 20 20'%3e%3cpath stroke='%23ffffff' stroke-linecap='round' stroke-linejoin='round' stroke-width='1.5' d='M6 8l4 4 4-4'/%3e%3c/svg%3e")`, backgroundPosition: 'right 0.25rem center', backgroundRepeat: 'no-repeat', backgroundSize: '1.25em 1.25em' }}
        >
          {AVAILABLE_MODELS.map(m => (
            <option key={m.id} value={m.id} className="bg-slate-900 text-slate-200">
              {m.label}
            </option>
          ))}
        </select>
        <div className="hidden group-hover:flex items-center text-[10px] text-white/40 px-2 bg-white/5 rounded backdrop-blur-sm border border-white/5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mr-2 animate-pulse"></span>
          LIVE INFERENCE
        </div>
      </div>

      <Plot
        data={[
          // Historical price line
          {
            x: chartData.historyDates,
            y: chartData.historyPrices,
            type: 'scatter',
            mode: 'lines',
            name: 'ZL Spot',
            line: { color: '#ffffff', width: 2 }, 
            hovertemplate: '%{x}<br>Spot: $%{y:.2f}<extra></extra>',
          },
          // P90 Bound (Invisible)
          {
            x: chartData.forecastDates,
            y: chartData.p90,
            type: 'scatter',
            mode: 'lines',
            name: 'P90',
            line: { width: 0, shape: 'spline' },
            showlegend: false,
            hoverinfo: 'skip'
          },
          // P10 Bound (Fill to P90)
          {
            x: chartData.forecastDates,
            y: chartData.p10,
            type: 'scatter',
            mode: 'lines',
            fill: 'tonexty',
            fillcolor: 'rgba(41, 98, 255, 0.08)', 
            name: 'Confidence (90%)',
            line: { width: 0, shape: 'spline' },
            showlegend: true,
            hoverinfo: 'skip'
          },
          // P75 Bound (Invisible)
          {
            x: chartData.forecastDates,
            y: chartData.p75,
            type: 'scatter',
            mode: 'lines',
            name: 'P75',
            line: { width: 0, shape: 'spline' },
            showlegend: false,
            hoverinfo: 'skip'
          },
          // P25 Bound (Fill to P75)
          {
            x: chartData.forecastDates,
            y: chartData.p25,
            type: 'scatter',
            mode: 'lines',
            fill: 'tonexty',
            fillcolor: 'rgba(41, 98, 255, 0.15)', 
            name: 'Likely Range (50%)',
            line: { width: 0, shape: 'spline' },
            showlegend: true,
            hoverinfo: 'skip'
          },
          // Prediction Line (Dynamic Color)
          {
            x: chartData.forecastDates,
            y: chartData.p50,
            type: 'scatter',
            mode: 'lines',
            name: selectedModel.label.split('(')[0].trim(),
            line: { color: selectedModel.color, width: 3, dash: 'dot', shape: 'spline' },
            hovertemplate: `%{x}<br>${selectedModel.label}: $%{y:.2f}<extra></extra>`,
          },
        ]}
        layout={{
          autosize: true,
          height: height,
          margin: { l: 40, r: 20, t: 30, b: 40 },
          paper_bgcolor: 'transparent',
          plot_bgcolor: 'transparent',
          font: { color: 'rgba(255, 255, 255, 0.8)', family: 'monospace' },
          images: [
            {
              source: "/chart_watermark.svg",
              xref: "paper",
              yref: "paper",
              x: 0.5,
              y: 0.5,
              sizex: isMobile ? 1 : 0.5,
              sizey: 1,
              sizing: "contain",
              opacity: 0.1,
              xanchor: "center",
              yanchor: "middle",
              layer: "below"
            }
          ],
          xaxis: {
            gridcolor: 'rgba(255,255,255,0.03)',
            linecolor: 'rgba(255,255,255,0.1)',
            zerolinecolor: 'rgba(255,255,255,0.1)',
            showgrid: true,
            gridwidth: 1,
          },
          yaxis: {
            gridcolor: 'rgba(255,255,255,0.03)',
            linecolor: 'rgba(255,255,255,0.1)',
            zerolinecolor: 'rgba(255,255,255,0.1)',
            tickprefix: '$',
            showgrid: true,
            gridwidth: 1,
          },
          legend: {
            orientation: 'h',
            y: 1.05,
            x: 0.3, // Shifted to make room for dropdown
            font: { size: 10 },
            bgcolor: 'rgba(0,0,0,0)'
          },
          hovermode: 'x unified',
          dragmode: 'pan',
          showlegend: true,
        }}
        config={{
          displayModeBar: false,
          responsive: true,
          scrollZoom: false,
        }}
        style={{ width: '100%', height: height }}
        useResizeHandler={true}
      />
    </div>
  )
}
```

## 3. Quant Admin Sidebar (`frontend/src/components/layout/QuantAdminSidebar.tsx`)

This component provides the overlay navigation and admin tools.

```tsx
'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  X, 
  Settings, 
  Database, 
  Cpu, 
  Activity, 
  GitBranch, 
  Users, 
  Shield, 
  LogOut 
} from 'lucide-react';

interface QuantAdminSidebarProps {
  isOpen: boolean;
  onClose: () => void;
  onLogout?: () => void;
}

export function QuantAdminSidebar({ isOpen, onClose, onLogout }: QuantAdminSidebarProps) {
  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-40"
          />

          {/* Sidebar */}
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="fixed top-0 right-0 bottom-0 w-80 bg-[#0a0a0a] border-l border-white/10 shadow-2xl z-50 flex flex-col"
          >
            {/* Header */}
            <div className="p-6 border-b border-white/5 flex items-center justify-between">
              <div>
                <h2 className="text-lg font-bold text-white tracking-tight">QUANT ADMIN</h2>
                <div className="text-[10px] text-slate-500 font-mono uppercase">System Control Plane</div>
              </div>
              <button 
                onClick={onClose}
                className="p-2 hover:bg-white/5 rounded-full text-slate-400 hover:text-white transition-colors"
              >
                <X size={18} />
              </button>
            </div>

            {/* Menu Items */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2">
               
               <div className="px-3 py-2 text-xs font-bold text-slate-600 uppercase tracking-widest mt-2 mb-1">
                   Core Infrastructure
               </div>
               
               <MenuItem icon={<Database size={16} />} label="Database Health" status="Healthy" />
               <MenuItem icon={<Cpu size={16} />} label="Model Registry" status="Active" />
               <MenuItem icon={<Activity size={16} />} label="Job Status" status="Idle" />

               <div className="px-3 py-2 text-xs font-bold text-slate-600 uppercase tracking-widest mt-6 mb-1">
                   Configuration
               </div>

               <MenuItem icon={<GitBranch size={16} />} label="Feature Flags" />
               <MenuItem icon={<Settings size={16} />} label="Global Config" />
               <MenuItem icon={<Shield size={16} />} label="Access Control" />
               
               <div className="px-3 py-2 text-xs font-bold text-slate-600 uppercase tracking-widest mt-6 mb-1">
                   User Management
               </div>
               
               <MenuItem icon={<Users size={16} />} label="Team Profiles" />
               
            </div>

            {/* Footer / User Profile */}
            <div className="p-4 border-t border-white/5 bg-zinc-900/30">
                <div className="flex items-center gap-3 mb-4">
                    <div className="w-10 h-10 rounded-full bg-gradient-to-br from-blue-500 to-indigo-600 border border-white/10 flex items-center justify-center text-white font-bold">
                        CM
                    </div>
                    <div>
                        <div className="text-sm font-bold text-white">Chris Mitchell</div>
                        <div className="text-xs text-slate-500">Head of Quant Strategy</div>
                    </div>
                </div>
                
                <button 
                    onClick={onLogout}
                    className="w-full flex items-center justify-center gap-2 p-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 text-xs font-bold rounded-lg border border-red-500/20 transition-colors"
                >
                    <LogOut size={14} />
                    SIGNOUT SYSTEM
                </button>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}

function MenuItem({ icon, label, status }: { icon: React.ReactNode, label: string, status?: string }) {
    return (
        <button className="w-full flex items-center justify-between p-3 rounded-lg hover:bg-white/5 text-slate-300 hover:text-white transition-all group">
            <div className="flex items-center gap-3">
                <div className="text-slate-500 group-hover:text-blue-400 transition-colors">{icon}</div>
                <span className="text-sm font-medium">{label}</span>
            </div>
            {status && (
                <span className={`text-[10px] px-1.5 py-0.5 rounded border ${
                    status === 'Healthy' || status === 'Active' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20' :
                    'bg-slate-500/10 text-slate-500 border-slate-500/20'
                }`}>
                    {status}
                </span>
            )}
        </button>
    )
}
```
