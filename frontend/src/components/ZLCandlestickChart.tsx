'use client'

import React, { useEffect, useRef, useState } from 'react'
import {
    SciChartSurface,
    NumericAxis,
    FastCandlestickRenderableSeries,
    FastBandRenderableSeries,
    OhlcDataSeries,
    XyyDataSeries,
    EAxisAlignment,
    EAutoRange,
    NumberRange,
    ENumericFormat,
    ZoomPanModifier,
    RolloverModifier,
    CursorModifier,
} from 'scichart'

interface PriceData {
    timestamp: string
    open: number
    high: number
    low: number
    close: number
    volume: number
}

// Custom dark theme for quant look
const quantThemeOverrides = {
    sciChartBackground: 'transparent',
    loadingAnimationBackground: 'transparent',
    axisBandsFill: 'transparent',
    axisTitleColor: 'rgba(255,255,255,0.4)',
    majorGridLineBrush: 'rgba(255,255,255,0.05)',
    minorGridLineBrush: 'transparent',
    tickTextBrush: 'rgba(255,255,255,0.35)',
    labelBackgroundBrush: 'rgba(20,10,40,0.9)',
    labelBorderBrush: 'rgba(139,92,246,0.5)',
    labelForegroundBrush: '#ffffff',
    cursorLineBrush: 'rgba(139,92,246,0.6)',
    rolloverLineStroke: 'rgba(139,92,246,0.6)',
}

export function ZLCandlestickChart({
    height = '70vh',
}: {
    height?: string | number
}) {
    const chartRef = useRef<HTMLDivElement>(null)
    const sciChartSurfaceRef = useRef<SciChartSurface | null>(null)
    const [priceData, setPriceData] = useState<PriceData[]>([])
    const [lastPrice, setLastPrice] = useState<number | null>(null)
    const [priceChange, setPriceChange] = useState<number>(0)
    const [volatility, setVolatility] = useState<string>('--')
    const [highPrice, setHighPrice] = useState<number | null>(null)
    const [lowPrice, setLowPrice] = useState<number | null>(null)
    const [isLive, setIsLive] = useState<boolean>(false)
    const [lastUpdate, setLastUpdate] = useState<string>('')
    const ohlcDataRef = useRef<OhlcDataSeries | null>(null)

    // Fetch historical data (daily bars)
    useEffect(() => {
        const fetchData = async () => {
            try {
                const res = await fetch('/api/zl/price-1d?days=365')
                if (!res.ok) throw new Error('Failed to fetch')
                const json = await res.json()
                if (json.data && json.data.length > 0) {
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

                    const highs = parsed.map((d: PriceData) => d.high)
                    const lows = parsed.map((d: PriceData) => d.low)
                    setHighPrice(Math.max(...highs))
                    setLowPrice(Math.min(...lows))

                    if (prev) {
                        setPriceChange(((latest.close - prev.close) / prev.close) * 100)
                    }
                    const last20 = parsed.slice(-20)
                    if (last20.length >= 2) {
                        const returns: number[] = []
                        for (let i = 1; i < last20.length; i++) {
                            returns.push(Math.log(last20[i].close / last20[i-1].close))
                        }
                        const mean = returns.reduce((a: number, b: number) => a + b, 0) / returns.length
                        const variance = returns.reduce((a: number, b: number) => a + Math.pow(b - mean, 2), 0) / returns.length
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
        // Refresh historical data every 15 minutes
        const interval = setInterval(fetchData, 900000)
        return () => clearInterval(interval)
    }, [])

    // Fetch live data (forming candle) - every 10 seconds
    useEffect(() => {
        const fetchLive = async () => {
            try {
                const res = await fetch('/api/zl/live')
                if (!res.ok) return
                const json = await res.json()
                
                if (json.price) {
                    setLastPrice(json.price)
                    setIsLive(json.source === 'databento_live')
                    if (json.updated_at) {
                        const updated = new Date(json.updated_at)
                        setLastUpdate(updated.toLocaleTimeString())
                    }
                    if (json.change_pct !== null) {
                        setPriceChange(json.change_pct)
                    }
                    
                    // Update the forming daily candle if we have the data series
                    if (json.forming_bars?.['1d'] && ohlcDataRef.current && priceData.length > 0) {
                        const forming = json.forming_bars['1d']
                        const lastIdx = priceData.length - 1
                        
                        // Update the last candle with live forming bar data
                        ohlcDataRef.current.update(
                            lastIdx,
                            forming.open,
                            forming.high,
                            forming.low,
                            forming.close
                        )
                        
                        // Update high/low if forming bar exceeds
                        if (forming.high > (highPrice || 0)) setHighPrice(forming.high)
                        if (forming.low < (lowPrice || Infinity)) setLowPrice(forming.low)
                    }
                }
            } catch (err) {
                // Silent fail for live updates
            }
        }
        
        fetchLive()
        // Poll live data every 10 seconds
        const liveInterval = setInterval(fetchLive, 10000)
        return () => clearInterval(liveInterval)
    }, [priceData, highPrice, lowPrice])

    // Initialize SciChart
    useEffect(() => {
        if (!chartRef.current || priceData.length === 0) return

        const initChart = async () => {
            // Clean up previous instance
            if (sciChartSurfaceRef.current) {
                sciChartSurfaceRef.current.delete()
            }

            // Configure WASM location and license
            SciChartSurface.useWasmFromCDN()
            SciChartSurface.setRuntimeLicenseKey('')

            const { sciChartSurface, wasmContext } = await SciChartSurface.create(
                chartRef.current!,
                { theme: { type: 'Navy', ...quantThemeOverrides } }
            )
            sciChartSurfaceRef.current = sciChartSurface

            // Calculate volatility bands (±1σ and ±2σ)
            const closes = priceData.map(d => d.close)
            const calcBands = () => {
                const lookback = 20
                const upper2: number[] = []
                const upper1: number[] = []
                const lower1: number[] = []
                const lower2: number[] = []

                for (let i = 0; i < closes.length; i++) {
                    if (i < lookback) {
                        upper2.push(closes[i])
                        upper1.push(closes[i])
                        lower1.push(closes[i])
                        lower2.push(closes[i])
                    } else {
                        const slice = closes.slice(i - lookback, i)
                        const mean = slice.reduce((a, b) => a + b, 0) / lookback
                        const variance = slice.reduce((a, b) => a + Math.pow(b - mean, 2), 0) / lookback
                        const std = Math.sqrt(variance)
                        upper2.push(mean + 2 * std)
                        upper1.push(mean + 1 * std)
                        lower1.push(mean - 1 * std)
                        lower2.push(mean - 2 * std)
                    }
                }
                return { upper2, upper1, lower1, lower2 }
            }

            const bands = calcBands()
            const xValues = priceData.map((_, i) => i)

            // X Axis - with padding so candles don't touch edges (like TradingView)
            const xAxis = new NumericAxis(wasmContext, {
                axisAlignment: EAxisAlignment.Bottom,
                autoRange: EAutoRange.Always,
                growBy: new NumberRange(0.02, 0.05), // 2% left padding, 5% right padding for last candle
                drawMajorBands: false,
                drawMinorGridLines: false,
                drawMajorGridLines: true,
                majorGridLineStyle: { color: 'rgba(255,255,255,0.05)', strokeThickness: 1 },
                axisBorder: { borderTop: 0, color: 'transparent' },
                labelStyle: { fontSize: 11, fontFamily: 'Inter', color: 'rgba(255,255,255,0.3)' },
            })
            sciChartSurface.xAxes.add(xAxis)

            // Y Axis - manually set range from data bounds with padding
            const allLows = priceData.map(d => d.low)
            const allHighs = priceData.map(d => d.high)
            const dataMin = Math.min(...allLows)
            const dataMax = Math.max(...allHighs)
            const dataRange = dataMax - dataMin
            const padding = dataRange * 0.1 // 10% padding

            const yAxis = new NumericAxis(wasmContext, {
                axisAlignment: EAxisAlignment.Right,
                autoRange: EAutoRange.Never,
                visibleRange: new NumberRange(dataMin - padding, dataMax + padding),
                drawMajorBands: false,
                drawMinorGridLines: false,
                drawMajorGridLines: true,
                majorGridLineStyle: { color: 'rgba(255,255,255,0.05)', strokeThickness: 1 },
                axisBorder: { borderLeft: 0, color: 'transparent' },
                labelStyle: { fontSize: 11, fontFamily: 'Inter', color: 'rgba(255,255,255,0.4)' },
                labelFormat: ENumericFormat.Decimal,
                labelPrecision: 2,
            })
            sciChartSurface.yAxes.add(yAxis)

            // 2σ Band (outer) - very subtle
            const band2Data = new XyyDataSeries(wasmContext, {
                xValues,
                yValues: bands.upper2,
                y1Values: bands.lower2,
            })
            const band2Series = new FastBandRenderableSeries(wasmContext, {
                dataSeries: band2Data,
                fill: 'rgba(139, 92, 246, 0.03)',
                fillY1: 'rgba(139, 92, 246, 0.03)',
                stroke: 'rgba(139, 92, 246, 0.08)',
                strokeY1: 'rgba(139, 92, 246, 0.08)',
                strokeThickness: 1,
            })
            sciChartSurface.renderableSeries.add(band2Series)

            // 1σ Band (inner) - slightly more visible
            const band1Data = new XyyDataSeries(wasmContext, {
                xValues,
                yValues: bands.upper1,
                y1Values: bands.lower1,
            })
            const band1Series = new FastBandRenderableSeries(wasmContext, {
                dataSeries: band1Data,
                fill: 'rgba(139, 92, 246, 0.05)',
                fillY1: 'rgba(139, 92, 246, 0.05)',
                stroke: 'rgba(139, 92, 246, 0.15)',
                strokeY1: 'rgba(139, 92, 246, 0.15)',
                strokeThickness: 1,
            })
            sciChartSurface.renderableSeries.add(band1Series)

            // Candlestick series - TradingView style colors
            // Up candles: cyan body (#26a69a / light blue), cyan wick
            // Down candles: pink/magenta body (#ef5350), pink wick
            const ohlcData = new OhlcDataSeries(wasmContext, {
                xValues,
                openValues: priceData.map(d => d.open),
                highValues: priceData.map(d => d.high),
                lowValues: priceData.map(d => d.low),
                closeValues: priceData.map(d => d.close),
            })
            
            // Store ref for live updates
            ohlcDataRef.current = ohlcData

            const candlestickSeries = new FastCandlestickRenderableSeries(wasmContext, {
                dataSeries: ohlcData,
                // Up candle (close > open) - lime green
                strokeUp: '#00ff00',           // Wick color for up
                brushUp: '#00ff00',            // Body fill for up
                // Down candle (close < open) - white
                strokeDown: '#ffffff',         // Wick color for down
                brushDown: '#ffffff',          // Body fill for down
                dataPointWidth: 0.7,
            })
            sciChartSurface.renderableSeries.add(candlestickSeries)

            // Add interactivity
            sciChartSurface.chartModifiers.add(
                new ZoomPanModifier({ enableZoom: false }),
                new RolloverModifier({
                    showTooltip: true,
                    showAxisLabel: true,
                    snapToDataPoint: true,
                }),
                new CursorModifier({
                    showTooltip: false,
                    showAxisLabels: true,
                    crosshairStroke: 'rgba(255, 255, 255, 0.3)',
                    crosshairStrokeThickness: 1,
                })
            )
        }

        initChart()

        // Handle resize
        const resizeObserver = new ResizeObserver(() => {
            if (sciChartSurfaceRef.current && chartRef.current) {
                sciChartSurfaceRef.current.changeViewportSize(
                    chartRef.current.clientWidth,
                    chartRef.current.clientHeight
                )
            }
        })
        if (chartRef.current) {
            resizeObserver.observe(chartRef.current)
        }

        return () => {
            resizeObserver.disconnect()
            if (sciChartSurfaceRef.current) {
                sciChartSurfaceRef.current.delete()
                sciChartSurfaceRef.current = null
            }
        }
    }, [priceData])

    return (
        <div className="relative w-full rounded-xl overflow-hidden border border-white/5" style={{ background: 'linear-gradient(180deg, #131722 0%, #0d1117 100%)' }}>
            {/* Header - compact */}
            <div className="flex items-center justify-between px-4 py-2 border-b border-white/5">
                <div className="flex items-center gap-3">
                    <div className="flex items-center gap-2">
                        <div className={`w-2 h-2 rounded-full ${isLive ? 'bg-green-400 animate-pulse shadow-lg shadow-green-400/50' : 'bg-cyan-400 animate-pulse shadow-lg shadow-cyan-400/50'}`} />
                        <span className="text-sm font-semibold text-white tracking-tight">ZL1!</span>
                        {isLive && (
                            <span className="px-1.5 py-0.5 text-[8px] font-bold bg-green-500/20 text-green-400 border border-green-500/30 rounded uppercase tracking-wider">
                                LIVE
                            </span>
                        )}
                    </div>
                    <span className="text-[11px] text-white/30 font-medium">Soybean Oil • 1D</span>
                    {lastUpdate && (
                        <span className="text-[9px] text-white/20 font-mono">{lastUpdate}</span>
                    )}
                    <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-violet-500/10 border border-violet-500/20">
                        <span className="text-[8px] text-violet-400 uppercase tracking-wider font-medium">±1σ/±2σ</span>
                    </div>
                </div>
                <div className="flex items-center gap-4">
                    {highPrice && lowPrice && (
                        <div className="flex items-center gap-3 text-[11px]">
                            <div className="flex items-center gap-1">
                                <span className="text-white/30">H</span>
                                <span className="text-white/60 font-mono">{highPrice.toFixed(2)}</span>
                            </div>
                            <div className="flex items-center gap-1">
                                <span className="text-white/30">L</span>
                                <span className="text-white/60 font-mono">{lowPrice.toFixed(2)}</span>
                            </div>
                        </div>
                    )}
                    <div className="h-3 w-px bg-white/10" />
                    <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-white/5">
                        <span className="text-[9px] text-white/30 uppercase">IV</span>
                        <span className="text-[11px] font-mono text-violet-400">{volatility}</span>
                    </div>
                    {lastPrice && (
                        <div className="flex items-center gap-2">
                            <span className="text-xl font-semibold text-white tabular-nums">{lastPrice.toFixed(2)}</span>
                            <span className={`text-xs font-medium tabular-nums ${priceChange >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                                {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* Chart area - takes remaining space */}
            <div className="relative w-full" style={{ height: `calc(${typeof height === 'number' ? height + 'px' : height} - 70px)` }}>
                {/* Watermark */}
                <div className="absolute inset-0 flex items-center justify-end pr-16 pointer-events-none z-0">
                    <img
                        src="/chart_watermark.svg"
                        alt=""
                        className="w-[300px] h-auto opacity-[0.03]"
                        style={{ filter: 'grayscale(100%) brightness(2)' }}
                    />
                </div>
                {/* SciChart Canvas */}
                <div
                    ref={chartRef}
                    className="absolute inset-0 z-10"
                />
            </div>

            {/* Legend - minimal */}
            <div className="flex items-center justify-center gap-6 px-4 py-1.5 border-t border-white/5 bg-black/20">
                <div className="flex items-center gap-1.5">
                    <div className="w-2.5 h-3 rounded-sm" style={{ backgroundColor: '#00ff00' }} />
                    <span className="text-[9px] text-white/40 uppercase">Bull</span>
                </div>
                <div className="flex items-center gap-1.5">
                    <div className="w-2.5 h-3 rounded-sm bg-white/80" />
                    <span className="text-[9px] text-white/40 uppercase">Bear</span>
                </div>
                <div className="flex items-center gap-1.5">
                    <div className="w-3 h-1.5 rounded-sm bg-violet-500/15 border border-violet-500/25" />
                    <span className="text-[9px] text-white/40 uppercase">Vol Bands</span>
                </div>
            </div>
        </div>
    )
}
