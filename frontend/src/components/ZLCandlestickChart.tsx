'use client'

import React, { useEffect, useRef, useState } from 'react'
import {
    SciChartSurface,
    NumericAxis,
    FastCandlestickRenderableSeries,
    FastBandRenderableSeries,
    FastLineRenderableSeries,
    OhlcDataSeries,
    XyyDataSeries,
    XyDataSeries,
    EAxisAlignment,
    EAutoRange,
    NumberRange,
    ENumericFormat,
    ZoomPanModifier,
    RolloverModifier,
    CursorModifier,
    NumericLabelProvider,
} from 'scichart'

interface PriceData {
    timestamp: string
    open: number
    high: number
    low: number
    close: number
    volume: number
}

interface ForecastPoint {
    horizon_days: number
    price_p30: number | null
    price_p50: number | null
    price_p70: number | null
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
    const [forecastData, setForecastData] = useState<ForecastPoint[]>([])
    const [lastPrice, setLastPrice] = useState<number | null>(null)
    const [priceChange, setPriceChange] = useState<number>(0)
    const [volatility, setVolatility] = useState<string>('--')
    const [highPrice, setHighPrice] = useState<number | null>(null)
    const [lowPrice, setLowPrice] = useState<number | null>(null)
    const [isLive, setIsLive] = useState<boolean>(false)
    const [lastUpdate, setLastUpdate] = useState<string>('')
    const [hasForecast, setHasForecast] = useState<boolean>(false)
    const ohlcDataRef = useRef<OhlcDataSeries | null>(null)

    // Fetch historical data (daily bars)
    useEffect(() => {
        const fetchData = async () => {
            try {
                const res = await fetch('/api/zl/price-1d?days=240') // ~8 months like TradingView screenshot
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

    // Fetch forecast data
    useEffect(() => {
        const fetchForecast = async () => {
            try {
                const res = await fetch('/api/zl/forecast')
                if (!res.ok) {
                    setHasForecast(false)
                    return
                }
                const json = await res.json()
                if (json.forecasts && json.forecasts.length > 0) {
                    setForecastData(json.forecasts)
                    setHasForecast(true)
                } else {
                    setHasForecast(false)
                }
            } catch (err) {
                console.error('Forecast fetch error:', err)
                setHasForecast(false)
            }
        }
        fetchForecast()
        // Refresh forecast every 5 minutes
        const interval = setInterval(fetchForecast, 300000)
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
                    
                    if (json.forming_bars?.['1d'] && ohlcDataRef.current && priceData.length > 0) {
                        const forming = json.forming_bars['1d']
                        const lastIdx = priceData.length - 1
                        ohlcDataRef.current.update(
                            lastIdx,
                            forming.open,
                            forming.high,
                            forming.low,
                            forming.close
                        )
                        if (forming.high > (highPrice || 0)) setHighPrice(forming.high)
                        if (forming.low < (lowPrice || Infinity)) setLowPrice(forming.low)
                    }
                }
            } catch (err) {
                // Silent fail for live updates
            }
        }
        
        fetchLive()
        const liveInterval = setInterval(fetchLive, 10000)
        return () => clearInterval(liveInterval)
    }, [priceData, highPrice, lowPrice])

    // Initialize SciChart
    useEffect(() => {
        if (!chartRef.current || priceData.length === 0) return

        const initChart = async () => {
            if (sciChartSurfaceRef.current) {
                sciChartSurfaceRef.current.delete()
            }

            SciChartSurface.useWasmFromCDN()
            SciChartSurface.setRuntimeLicenseKey('')

            const { sciChartSurface, wasmContext } = await SciChartSurface.create(
                chartRef.current!,
                { theme: { type: 'Navy', ...quantThemeOverrides } }
            )
            sciChartSurfaceRef.current = sciChartSurface

            const xValues = priceData.map((_, i) => i)
            const lastCandleIdx = priceData.length - 1
            const currentPrice = priceData[lastCandleIdx].close

            // Build forecast fan data (starts at current price, extends into future)
            // X positions: current candle, then future points at horizons
            const forecastXValues: number[] = [lastCandleIdx]
            const forecastP50: number[] = [currentPrice]
            const forecastP30: number[] = [currentPrice]
            const forecastP70: number[] = [currentPrice]

            if (hasForecast && forecastData.length > 0) {
                // Map horizon days to approximate x position (1 candle = 1 day)
                for (const fc of forecastData) {
                    if (fc.price_p30 !== null && fc.price_p50 !== null && fc.price_p70 !== null) {
                        forecastXValues.push(lastCandleIdx + fc.horizon_days)
                        forecastP50.push(fc.price_p50)
                        forecastP30.push(fc.price_p30)
                        forecastP70.push(fc.price_p70)
                    }
                }
            }

            // Calculate Y-axis range including forecast cone
            const candleHighs = priceData.map(d => d.high)
            const candleLows = priceData.map(d => d.low)
            let yMin = Math.min(...candleLows)
            let yMax = Math.max(...candleHighs)
            
            // Extend Y range if forecast data exists
            if (forecastP70.length > 1) {
                yMax = Math.max(yMax, ...forecastP70)
                yMin = Math.min(yMin, ...forecastP30)
            }
            
            const yRange = yMax - yMin
            const paddingAmount = yRange * 0.05 // Tighter fit like TradingView

            // X Axis - show actual dates
            const dateLabelProvider = new NumericLabelProvider()
            dateLabelProvider.formatLabel = (dataValue: number) => {
                const idx = Math.round(dataValue)
                if (idx >= 0 && idx < priceData.length) {
                    const date = new Date(priceData[idx].timestamp)
                    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
                }
                return ''
            }
            dateLabelProvider.formatCursorLabel = (dataValue: number) => {
                const idx = Math.round(dataValue)
                if (idx >= 0 && idx < priceData.length) {
                    const date = new Date(priceData[idx].timestamp)
                    return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
                }
                return ''
            }

            const xAxis = new NumericAxis(wasmContext, {
                axisAlignment: EAxisAlignment.Bottom,
                autoRange: EAutoRange.Always,
                growBy: new NumberRange(0.005, 0.02),
                drawMajorBands: false,
                drawMinorGridLines: false,
                drawMajorGridLines: true,
                majorGridLineStyle: { color: 'rgba(255,255,255,0.05)', strokeThickness: 1 },
                axisBorder: { borderTop: 0, color: 'transparent' },
                labelStyle: { fontSize: 11, fontFamily: 'Inter', color: 'rgba(255,255,255,0.3)' },
                labelProvider: dateLabelProvider,
            })
            sciChartSurface.xAxes.add(xAxis)

            const yAxis = new NumericAxis(wasmContext, {
                axisAlignment: EAxisAlignment.Right,
                autoRange: EAutoRange.Never,
                visibleRange: new NumberRange(yMin - paddingAmount, yMax + paddingAmount),
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

            // Forecast Fan (p30-p70 band) - only if we have forecast data
            if (forecastXValues.length > 1) {
                const forecastBandData = new XyyDataSeries(wasmContext, {
                    xValues: forecastXValues,
                    yValues: forecastP70,
                    y1Values: forecastP30,
                })
                const forecastBandSeries = new FastBandRenderableSeries(wasmContext, {
                    dataSeries: forecastBandData,
                    fill: 'rgba(236, 72, 153, 0.15)', // Pink/magenta fill
                    fillY1: 'rgba(236, 72, 153, 0.15)',
                    stroke: 'rgba(236, 72, 153, 0.4)',
                    strokeY1: 'rgba(236, 72, 153, 0.4)',
                    strokeThickness: 1,
                })
                sciChartSurface.renderableSeries.add(forecastBandSeries)

                // P50 center line (median forecast)
                const forecastLineData = new XyDataSeries(wasmContext, {
                    xValues: forecastXValues,
                    yValues: forecastP50,
                })
                const forecastLineSeries = new FastLineRenderableSeries(wasmContext, {
                    dataSeries: forecastLineData,
                    stroke: 'rgba(236, 72, 153, 0.8)',
                    strokeThickness: 2,
                    strokeDashArray: [5, 3], // Dashed line for forecast
                })
                sciChartSurface.renderableSeries.add(forecastLineSeries)
            }

            // Candlestick series
            const ohlcData = new OhlcDataSeries(wasmContext, {
                xValues,
                openValues: priceData.map(d => d.open),
                highValues: priceData.map(d => d.high),
                lowValues: priceData.map(d => d.low),
                closeValues: priceData.map(d => d.close),
            })
            ohlcDataRef.current = ohlcData

            // Green: solid fill + white wick | Down: hollow with white outline/wick
            const candlestickSeries = new FastCandlestickRenderableSeries(wasmContext, {
                dataSeries: ohlcData,
                strokeUp: '#ffffff',      // White wick for green (up) candles
                brushUp: '#00ff00',       // Solid green fill
                strokeDown: '#ffffff',    // White outline + wick for hollow candles
                brushDown: 'transparent', // Hollow - no fill
                dataPointWidth: 0.5,
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

        const resizeObserver = new ResizeObserver((entries) => {
            if (sciChartSurfaceRef.current && entries[0]) {
                const { width, height } = entries[0].contentRect;
                sciChartSurfaceRef.current.changeViewportSize(width, height);
            }
        })
        if (chartRef.current?.parentElement) {
            resizeObserver.observe(chartRef.current.parentElement)
        }

        return () => {
            resizeObserver.disconnect()
            if (sciChartSurfaceRef.current) {
                sciChartSurfaceRef.current.delete()
                sciChartSurfaceRef.current = null
            }
        }
    }, [priceData, forecastData, hasForecast])

    return (
        <div 
            className="relative w-full rounded-xl overflow-hidden border border-white/5 flex flex-col" 
            style={{ 
                background: 'linear-gradient(180deg, #131722 0%, #0d1117 100%)',
                height: typeof height === 'number' ? `${height}px` : height 
            }}
        >
            {/* Header - compact */}
            <div className="flex-shrink-0 flex items-center justify-between px-4 py-2 border-b border-white/5">
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
                    {hasForecast && (
                        <div className="flex items-center gap-1 px-1.5 py-0.5 rounded bg-pink-500/10 border border-pink-500/20">
                            <span className="text-[8px] text-pink-400 uppercase tracking-wider font-medium">Core Model</span>
                        </div>
                    )}
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

            {/* Chart area */}
            <div className="relative w-full flex-1 min-h-0">
                <div className="absolute inset-0 flex items-center justify-end pr-16 pointer-events-none z-0">
                    <img
                        src="/chart_watermark.svg"
                        alt=""
                        className="w-[300px] h-auto opacity-[0.03]"
                        style={{ filter: 'grayscale(100%) brightness(2)' }}
                    />
                </div>
                <div
                    ref={chartRef}
                    style={{ width: '100%', height: '100%', position: 'absolute', top: 0, left: 0 }}
                />
            </div>

            {/* Legend */}
            <div className="flex-shrink-0 flex items-center justify-center gap-6 px-4 py-1.5 border-t border-white/5 bg-black/20">
                <div className="flex items-center gap-1.5">
                    <div className="w-2.5 h-3 rounded-sm" style={{ backgroundColor: '#00ff00' }} />
                    <span className="text-[9px] text-white/40 uppercase">Bull</span>
                </div>
                <div className="flex items-center gap-1.5">
                    <div className="w-2.5 h-3 rounded-sm bg-white" />
                    <span className="text-[9px] text-white/40 uppercase">Bear</span>
                </div>
                {hasForecast && (
                    <>
                        <div className="flex items-center gap-1.5">
                            <div className="w-3 h-1.5 rounded-sm bg-pink-500/30 border border-pink-500/50" />
                            <span className="text-[9px] text-white/40 uppercase">P30-P70</span>
                        </div>
                        <div className="flex items-center gap-1.5">
                            <div className="w-3 h-0.5 bg-pink-400" style={{ borderTop: '2px dashed' }} />
                            <span className="text-[9px] text-white/40 uppercase">P50 (Median)</span>
                        </div>
                    </>
                )}
            </div>
        </div>
    )
}
