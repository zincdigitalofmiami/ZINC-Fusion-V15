'use client'

import React, { useEffect, useRef, useState } from 'react'
import {
    createChart,
    LineSeries,
    HistogramSeries,
    ColorType,
    IChartApi,
    UTCTimestamp,
    LineStyle,
} from 'lightweight-charts'

interface PriceData {
    timestamp: string
    open: number
    high: number
    low: number
    close: number
    volume: number
}

export function ZLCandlestickChart({
    height = '70vh',
}: {
    height?: string | number
}) {
    const chartContainerRef = useRef<HTMLDivElement>(null)
    const chartRef = useRef<IChartApi | null>(null)
    const [priceData, setPriceData] = useState<PriceData[]>([])
    const [lastPrice, setLastPrice] = useState<number | null>(null)
    const [priceChange, setPriceChange] = useState<number>(0)
    const [volatility, setVolatility] = useState<string>('--')

    // Fetch data
    useEffect(() => {
        const fetchData = async () => {
            try {
                const res = await fetch('/api/zl/price-1d?days=120')
                if (!res.ok) throw new Error('Failed to fetch')
                const json = await res.json()
                if (json.data && json.data.length > 0) {
                    // Parse numeric strings to floats (PostgreSQL numeric comes as string)
                    const parsed = json.data.map((d: PriceData) => ({
                        ...d,
                        open: parseFloat(String(d.open)),
                        high: parseFloat(String(d.high)),
                        low: parseFloat(String(d.low)),
                        close: parseFloat(String(d.close)),
                        volume: parseFloat(String(d.volume)),
                    }))
                    setPriceData(parsed)
                    const latest = parsed[parsed.length - 1]
                    const prev = parsed[parsed.length - 2]
                    setLastPrice(latest.close)
                    if (prev) {
                        setPriceChange(((latest.close - prev.close) / prev.close) * 100)
                    }
                    // Calculate 20-day realized volatility
                    const last20 = json.data.slice(-20)
                    if (last20.length >= 2) {
                        const returns = []
                        for (let i = 1; i < last20.length; i++) {
                            returns.push(Math.log(last20[i].close / last20[i-1].close))
                        }
                        const mean = returns.reduce((a, b) => a + b, 0) / returns.length
                        const variance = returns.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / returns.length
                        const dailyVol = Math.sqrt(variance)
                        const annualizedVol = dailyVol * Math.sqrt(252) * 100
                        setVolatility(annualizedVol.toFixed(1) + '%')
                    }
                }
            } catch (err) {
                console.error('Fetch error:', err)
            }
        }
        fetchData()
        const interval = setInterval(fetchData, 900000)
        return () => clearInterval(interval)
    }, [])

    // Initialize & Update Chart
    useEffect(() => {
        if (!chartContainerRef.current || priceData.length === 0) return

        if (chartRef.current) {
            chartRef.current.remove()
        }

        const containerWidth = chartContainerRef.current.clientWidth
        const containerHeight = chartContainerRef.current.clientHeight

        const chart = createChart(chartContainerRef.current, {
            width: containerWidth,
            height: containerHeight,
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#525252',
                attributionLogo: false,
                fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
            },
            grid: {
                vertLines: { visible: false },
                horzLines: { color: 'rgba(255,255,255,0.03)', style: LineStyle.Solid },
            },
            handleScroll: {
                mouseWheel: false,
                pressedMouseMove: true,
                horzTouchDrag: true,
                vertTouchDrag: false,
            },
            handleScale: {
                mouseWheel: false,
                pinch: true,
                axisPressedMouseMove: true,
            },
            crosshair: {
                vertLine: { color: 'rgba(0,212,255,0.4)', width: 1, style: LineStyle.Dashed, labelVisible: true, labelBackgroundColor: '#0a0a0a' },
                horzLine: { color: 'rgba(0,212,255,0.4)', width: 1, style: LineStyle.Dashed, labelVisible: true, labelBackgroundColor: '#0a0a0a' },
            },
            timeScale: {
                visible: true,
                borderVisible: false,
                fixLeftEdge: false,
                fixRightEdge: false,
                timeVisible: true,
                rightOffset: 5,
                barSpacing: 8,
                minBarSpacing: 2,
            },
            rightPriceScale: {
                borderVisible: false,
                scaleMargins: { top: 0.1, bottom: 0.2 },
                autoScale: true,
            },
        })

        chartRef.current = chart

        // Transform data
        const lineData = priceData.map(d => ({
            time: Math.floor(new Date(d.timestamp).getTime() / 1000) as UTCTimestamp,
            value: d.close,
        })).sort((a, b) => (a.time as number) - (b.time as number))

        // Calculate momentum for coloring (5-day ROC)
        const momentumData = priceData.map((d, i) => {
            const time = Math.floor(new Date(d.timestamp).getTime() / 1000) as UTCTimestamp
            const lookback = Math.max(0, i - 5)
            const roc = ((d.close - priceData[lookback].close) / priceData[lookback].close) * 100
            // Normalize volume for display
            const maxVol = Math.max(...priceData.map(p => p.volume))
            const normVol = (d.volume / maxVol) * (d.close * 0.15)

            // Color based on momentum: green for positive, red for negative, intensity by magnitude
            let color: string
            if (roc > 2) color = 'rgba(34, 197, 94, 0.6)'      // Strong bullish
            else if (roc > 0.5) color = 'rgba(34, 197, 94, 0.35)'  // Mild bullish
            else if (roc > -0.5) color = 'rgba(100, 100, 100, 0.2)' // Neutral
            else if (roc > -2) color = 'rgba(239, 68, 68, 0.35)'   // Mild bearish
            else color = 'rgba(239, 68, 68, 0.6)'              // Strong bearish

            return { time, value: normVol, color }
        }).sort((a, b) => (a.time as number) - (b.time as number))

        // Volume/Momentum histogram in background
        const volumeSeries = chart.addSeries(HistogramSeries, {
            priceLineVisible: false,
            lastValueVisible: false,
            priceFormat: { type: 'volume' },
        })
        volumeSeries.setData(momentumData)

        // Main price line - crisp cyan with glow effect via area
        const priceArea = chart.addSeries(LineSeries, {
            color: '#00D4FF',
            lineWidth: 2,
            priceLineVisible: true,
            priceLineColor: '#00D4FF',
            priceLineWidth: 1,
            priceLineStyle: LineStyle.Dashed,
            crosshairMarkerVisible: true,
            crosshairMarkerRadius: 5,
            crosshairMarkerBackgroundColor: '#00D4FF',
            crosshairMarkerBorderColor: '#ffffff',
            crosshairMarkerBorderWidth: 2,
            lastValueVisible: true,
        })
        priceArea.setData(lineData)

        // Fit and subscribe to range changes
        chart.timeScale().fitContent()

        chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
            chart.priceScale('right').applyOptions({ autoScale: true })
        })

        const resizeObserver = new ResizeObserver((entries) => {
            if (entries.length === 0 || !entries[0].target) return
            const newRect = entries[0].contentRect
            chart.applyOptions({ width: newRect.width, height: newRect.height })
        })
        resizeObserver.observe(chartContainerRef.current)

        return () => {
            resizeObserver.disconnect()
            chart.remove()
        }
    }, [priceData])

    return (
        <div className="relative w-full bg-gradient-to-b from-[#0a0a0a] to-[#050508] rounded-xl overflow-hidden border border-white/5">
            {/* Header with live stats */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-white/5">
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse" />
                        <span className="text-sm font-mono text-white/90 tracking-wide">ZL1!</span>
                    </div>
                    <span className="text-xs text-slate-500">Soybean Oil Futures • Daily</span>
                </div>
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2 px-2 py-1 rounded bg-white/5">
                        <span className="text-[10px] text-slate-500 uppercase">Vol</span>
                        <span className="text-xs font-mono text-amber-400">{volatility}</span>
                    </div>
                    {lastPrice && (
                        <div className="flex items-center gap-2">
                            <span className="text-lg font-mono text-white">${lastPrice.toFixed(2)}</span>
                            <span className={`text-xs font-mono ${priceChange >= 0 ? 'text-emerald-400' : 'text-red-400'}`}>
                                {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* Chart Container */}
            <div
                ref={chartContainerRef}
                className="w-full relative"
                style={{ height: typeof height === 'number' ? `${height}px` : height }}
            >
                {/* Subtle gradient overlay for depth */}
                <div className="absolute inset-0 pointer-events-none bg-gradient-to-t from-[#0a0a0a]/80 via-transparent to-transparent z-10" />
                {/* Watermark */}
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                    <div className="text-8xl font-black text-white/[0.015] tracking-[0.2em]">ZINC</div>
                </div>
            </div>

            {/* Footer with indicators */}
            <div className="flex items-center justify-between px-4 py-2 border-t border-white/5 bg-black/20">
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-1.5">
                        <div className="w-3 h-1.5 rounded-sm bg-emerald-500/60" />
                        <span className="text-[9px] text-slate-500 uppercase">Bullish Momentum</span>
                    </div>
                    <div className="flex items-center gap-1.5">
                        <div className="w-3 h-1.5 rounded-sm bg-red-500/60" />
                        <span className="text-[9px] text-slate-500 uppercase">Bearish Momentum</span>
                    </div>
                </div>
                <div className="flex items-center gap-1.5">
                    <div className="w-3 h-0.5 bg-cyan-400" />
                    <span className="text-[9px] text-slate-500 uppercase">Price</span>
                </div>
            </div>
        </div>
    )
}
