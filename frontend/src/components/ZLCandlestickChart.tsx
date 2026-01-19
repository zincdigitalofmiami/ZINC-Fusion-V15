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

    // Fetch data
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
        const interval = setInterval(fetchData, 900000)
        return () => clearInterval(interval)
    }, [])

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

            // X Axis
            const xAxis = new NumericAxis(wasmContext, {
                axisAlignment: EAxisAlignment.Bottom,
                autoRange: EAutoRange.Always,
                drawMajorBands: false,
                drawMinorGridLines: false,
                drawMajorGridLines: true,
                majorGridLineStyle: { color: 'rgba(255,255,255,0.05)', strokeThickness: 1 },
                axisBorder: { borderTop: 0, color: 'transparent' },
                labelStyle: { fontSize: 11, fontFamily: 'Inter', color: 'rgba(255,255,255,0.3)' },
            })
            sciChartSurface.xAxes.add(xAxis)

            // Y Axis
            const yAxis = new NumericAxis(wasmContext, {
                axisAlignment: EAxisAlignment.Right,
                autoRange: EAutoRange.Always,
                growBy: new NumberRange(0.1, 0.1),
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

            const candlestickSeries = new FastCandlestickRenderableSeries(wasmContext, {
                dataSeries: ohlcData,
                // Up candle (close > open) - cyan/teal
                strokeUp: '#53b9c7',           // Wick color for up
                brushUp: '#53b9c7',            // Body fill for up (73% opacity in settings)
                // Down candle (close < open) - pink/magenta
                strokeDown: '#e45f93',         // Wick color for down
                brushDown: '#e45f93',          // Body fill for down
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

        return () => {
            if (sciChartSurfaceRef.current) {
                sciChartSurfaceRef.current.delete()
                sciChartSurfaceRef.current = null
            }
        }
    }, [priceData])

    return (
        <div className="relative w-full rounded-2xl overflow-hidden border border-white/5" style={{ background: 'linear-gradient(180deg, #131722 0%, #0d1117 100%)' }}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-white/5">
                <div className="flex items-center gap-4">
                    <div className="flex items-center gap-2">
                        <div className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse shadow-lg shadow-cyan-400/50" />
                        <span className="text-base font-semibold text-white tracking-tight">ZL1!</span>
                    </div>
                    <span className="text-xs text-white/30 font-medium">Soybean Oil Futures • 1D</span>
                    <div className="flex items-center gap-2 px-2 py-0.5 rounded bg-violet-500/10 border border-violet-500/20">
                        <span className="text-[9px] text-violet-400 uppercase tracking-wider font-medium">±1σ / ±2σ</span>
                    </div>
                </div>
                <div className="flex items-center gap-6">
                    {highPrice && lowPrice && (
                        <div className="flex items-center gap-4 text-xs">
                            <div className="flex items-center gap-1.5">
                                <span className="text-white/30">H</span>
                                <span className="text-white/60 font-mono">{highPrice.toFixed(2)}</span>
                            </div>
                            <div className="flex items-center gap-1.5">
                                <span className="text-white/30">L</span>
                                <span className="text-white/60 font-mono">{lowPrice.toFixed(2)}</span>
                            </div>
                        </div>
                    )}
                    <div className="h-4 w-px bg-white/10" />
                    <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-white/5">
                        <span className="text-[10px] text-white/30 uppercase tracking-wider">IV</span>
                        <span className="text-xs font-mono text-violet-400">{volatility}</span>
                    </div>
                    {lastPrice && (
                        <div className="flex items-center gap-3">
                            <span className="text-2xl font-semibold text-white tabular-nums">{lastPrice.toFixed(2)}</span>
                            <span className={`text-sm font-medium tabular-nums ${priceChange >= 0 ? 'text-cyan-400' : 'text-pink-400'}`}>
                                {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                            </span>
                        </div>
                    )}
                </div>
            </div>

            {/* Chart */}
            <div
                ref={chartRef}
                className="w-full"
                style={{ height: typeof height === 'number' ? `${height}px` : height }}
            />

            {/* Legend */}
            <div className="flex items-center justify-center gap-8 px-6 py-3 border-t border-white/5 bg-black/20">
                <div className="flex items-center gap-2">
                    <div className="w-3 h-4 rounded-sm bg-cyan-400/80" />
                    <span className="text-[10px] text-white/40 uppercase tracking-wider">Bullish</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-3 h-4 rounded-sm bg-pink-400/80" />
                    <span className="text-[10px] text-white/40 uppercase tracking-wider">Bearish</span>
                </div>
                <div className="flex items-center gap-2">
                    <div className="w-4 h-2 rounded-sm bg-violet-500/15 border border-violet-500/25" />
                    <span className="text-[10px] text-white/40 uppercase tracking-wider">±1σ / ±2σ</span>
                </div>
            </div>
        </div>
    )
}
