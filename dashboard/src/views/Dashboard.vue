<template>
  <div class="dashboard">
    <!-- HERO SECTION -->
    <section class="hero">
      <!-- Ticker Header -->
      <div class="ticker-header">
        <div class="ticker-info">
          <span class="ticker-symbol">ZL</span>
          <span class="ticker-name">Soybean Oil Futures</span>
          <span class="ticker-price" :class="priceChange >= 0 ? 'up' : 'down'">
            {{ currentPrice.toFixed(2) }}
          </span>
          <span class="ticker-change" :class="priceChange >= 0 ? 'up' : 'down'">
            {{ priceChange >= 0 ? '+' : '' }}{{ priceChangePercent.toFixed(2) }}%
          </span>
        </div>
        <div class="ticker-meta">
          <span class="meta-label">L5 Monte Carlo Consensus</span>
          <span class="meta-value">10K Simulations</span>
        </div>
      </div>

      <!-- Horizon Tabs + Probability Legend -->
      <div class="chart-controls">
        <div class="horizon-tabs">
          <button
            v-for="h in horizons"
            :key="h.key"
            :class="{ active: activeHorizon === h.key }"
            @click="setHorizon(h.key)"
          >{{ h.label }}</button>
        </div>
        <div class="probability-legend">
          <span class="legend-item p90"><span class="legend-dot"></span>P90 Ceiling</span>
          <span class="legend-item p50"><span class="legend-dot"></span>P50 Median</span>
          <span class="legend-item p10"><span class="legend-dot"></span>P10 Floor</span>
        </div>
      </div>

      <!-- Hero Chart Container -->
      <div class="hero-chart-wrapper">
        <!-- Massive ticker watermark behind chart -->
        <div class="ticker-watermark">ZL</div>
        <!-- ZINC Digital Watermark -->
        <div class="chart-watermark">
          <img v-if="logoUrl" :src="logoUrl" alt="ZINC Digital" class="watermark-logo" />
        </div>
        <div class="hero-chart" ref="heroChartRef"></div>

        <!-- Current Price Tag with pulse -->
        <div class="current-price-tag" :class="priceChange >= 0 ? 'up' : 'down'" v-if="currentPrice > 0">
          <span class="price-pulse"></span>
          <span class="price-value">{{ currentPrice.toFixed(2) }}</span>
        </div>

        <!-- Probability Bands Overlay -->
        <div class="prob-bands" v-if="forecastData.p90.length > 0">
          <div class="prob-band p90-label">
            <span class="band-value">{{ forecastData.p90[forecastData.p90.length - 1]?.value.toFixed(2) }}</span>
            <span class="band-label">90%</span>
          </div>
          <div class="prob-band p50-label">
            <span class="band-value">{{ forecastData.p50[forecastData.p50.length - 1]?.value.toFixed(2) }}</span>
            <span class="band-label">50%</span>
          </div>
          <div class="prob-band p10-label">
            <span class="band-value">{{ forecastData.p10[forecastData.p10.length - 1]?.value.toFixed(2) }}</span>
            <span class="band-label">10%</span>
          </div>
        </div>
      </div>
    </section>

    <!-- L3 SPECIALIST INTELLIGENCE -->
    <section class="specialists-section">
      <div class="section-header">
        <h2>L3 SPECIALIST INTELLIGENCE</h2>
        <span class="section-meta">10 Domain Experts - Real-time LASSO Weights</span>
      </div>

      <div class="specialists-grid">
        <!-- FUSION POSTURE - Aggregate (2 columns wide) -->
        <div class="posture-card" :class="aggregatePosture.class + '-accent'">
          <!-- Compact Header Row -->
          <div class="posture-header-row">
            <div class="posture-header-left">
              <span class="posture-title">FUSION POSTURE</span>
              <span class="posture-subtitle">10 Specialist Aggregate</span>
            </div>
            <span class="status-badge large" :class="aggregatePosture.class.replace('strong-', '')">
              {{ aggregatePosture.label.toUpperCase() }}
            </span>
          </div>

          <!-- Meter + Counts Row -->
          <div class="posture-content">
            <div class="posture-meter-container">
              <div class="posture-meter">
                <div class="meter-track">
                  <div class="meter-segment sell"></div>
                  <div class="meter-segment neutral"></div>
                  <div class="meter-segment buy"></div>
                </div>
                <div class="meter-indicator" :style="{ left: getMeterPosition() + '%' }"></div>
              </div>
              <div class="meter-labels">
                <span class="meter-label sell">SELL</span>
                <span class="meter-label neutral">NEUTRAL</span>
                <span class="meter-label buy">BUY</span>
              </div>
            </div>

            <div class="posture-counts">
              <div class="count-item bearish">
                <span class="count-value">{{ signalCounts.bearish }}</span>
                <span class="count-label">Bearish</span>
              </div>
              <div class="count-item neutral">
                <span class="count-value">{{ signalCounts.neutral }}</span>
                <span class="count-label">Neutral</span>
              </div>
              <div class="count-item bullish">
                <span class="count-value">{{ signalCounts.bullish }}</span>
                <span class="count-label">Bullish</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Individual Specialist Cards -->
        <div
          v-for="spec in specialists"
          :key="spec.id"
          class="specialist-card"
          :class="[getSignalClass(spec.signal) + '-accent']"
        >
          <!-- Card Header: Title + Controls + Badge in one row -->
          <div class="spec-card-header">
            <div class="spec-header-left">
              <span class="spec-name">{{ spec.name }}</span>
              <span class="spec-description">{{ spec.description }}</span>
            </div>
            <div class="spec-header-right">
              <!-- Status Badge -->
              <span class="status-badge" :class="getSignalClass(spec.signal)">
                {{ getSignalLabel(spec.signal) }}
              </span>
            </div>
          </div>

          <!-- Mini Sparkline Chart -->
          <div class="spec-mini-chart" :ref="el => specChartRefs[spec.id] = el"></div>

          <!-- Signal Row: Meter + Value -->
          <div class="spec-signal-row">
            <div class="spec-meter">
              <div class="spec-meter-track">
                <div class="spec-meter-fill" :class="getSignalClass(spec.signal)" :style="{ width: getSpecMeterWidth(spec.signal) + '%', left: spec.signal < 0 ? 'auto' : '50%', right: spec.signal < 0 ? '50%' : 'auto' }"></div>
              </div>
              <div class="spec-meter-center"></div>
            </div>
            <span class="signal-value" :class="getSignalClass(spec.signal)">
              {{ spec.signal >= 0 ? '+' : '' }}{{ spec.signal.toFixed(3) }}
            </span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { createChart, LineSeries, AreaSeries } from 'lightweight-charts'

const API_BASE = ''
const logoUrl = ref(null)

const activeHorizon = ref('21D')
const horizons = [
  { key: '5D', label: '5D', days: 5 },
  { key: '21D', label: '21D', days: 21 },
  { key: '63D', label: '63D', days: 63 },
  { key: '126D', label: '126D', days: 126 }
]

const currentPrice = ref(0)
const priceChange = ref(0)
const priceChangePercent = ref(0)
const priceHistory = ref([])
const forecastData = ref({ p10: [], p50: [], p90: [] })

const specialists = ref([
  { id: 'crush', name: 'Crush', description: 'Processor margins & meal/oil ratio', signal: 0, direction: 'neutral', history: [] },
  { id: 'china', name: 'China', description: 'Import demand & stockpiles', signal: 0, direction: 'neutral', history: [] },
  { id: 'energy', name: 'Energy', description: 'Crude & Diesel correlation', signal: 0, direction: 'neutral', history: [] },
  { id: 'fx', name: 'FX', description: 'USD Strength & EM Crosses', signal: 0, direction: 'neutral', history: [] },
  { id: 'fed', name: 'Fed', description: 'Yield Curve & Liquidity', signal: 0, direction: 'neutral', history: [] },
  { id: 'tariff', name: 'Tariff', description: 'Trade Policy & Duties', signal: 0, direction: 'neutral', history: [] },
  { id: 'biofuel', name: 'Biofuel', description: 'RINs & Mandates', signal: 0, direction: 'neutral', history: [] },
  { id: 'palm', name: 'Palm', description: 'Malaysian Supply', signal: 0, direction: 'neutral', history: [] },
  { id: 'volatility', name: 'Volatility', description: 'Regime Detection', signal: 0, direction: 'neutral', history: [] },
  { id: 'substitutes', name: 'Substitute', description: 'Canola/Sunflower Spreads', signal: 0, direction: 'neutral', history: [] }
])

const aggregateSignal = computed(() => {
  const signals = specialists.value.map(s => s.signal)
  return signals.reduce((a, b) => a + b, 0) / signals.length
})

const aggregatePosture = computed(() => {
  const sig = aggregateSignal.value
  if (sig > 0.03) return { label: 'Strong Buy', class: 'strong-bullish' }
  if (sig > 0.01) return { label: 'Buy', class: 'bullish' }
  if (sig < -0.03) return { label: 'Strong Sell', class: 'strong-bearish' }
  if (sig < -0.01) return { label: 'Sell', class: 'bearish' }
  return { label: 'Neutral', class: 'neutral' }
})

const signalCounts = computed(() => {
  let bullish = 0, neutral = 0, bearish = 0
  specialists.value.forEach(s => {
    if (s.signal > 0.01) bullish++
    else if (s.signal < -0.01) bearish++
    else neutral++
  })
  return { bullish, neutral, bearish }
})

function getMeterPosition() {
  const sig = Math.max(-0.1, Math.min(0.1, aggregateSignal.value))
  return ((sig + 0.1) / 0.2) * 100
}

function getSpecMeterWidth(signal) {
  const sig = Math.abs(Math.max(-0.1, Math.min(0.1, signal)))
  return (sig / 0.1) * 50
}

const heroChartRef = ref(null)
const specChartRefs = ref({})
let heroChart = null
const specCharts = {}

function getSignalClass(signal) {
  if (signal > 0.01) return 'bullish'
  if (signal < -0.01) return 'bearish'
  return 'neutral'
}

function getSignalLabel(signal) {
  if (signal > 0.03) return 'STRONG BUY'
  if (signal > 0.01) return 'BUY'
  if (signal < -0.03) return 'STRONG SELL'
  if (signal < -0.01) return 'SELL'
  return 'NEUTRAL'
}

function setHorizon(key) {
  activeHorizon.value = key
}

async function fetchPriceData() {
  try {
    const horizon = horizons.find(h => h.key === activeHorizon.value)
    const days = Math.max(horizon.days + 60, 90)
    const res = await fetch(`${API_BASE}/api/zl/price?days=${days}`)
    const data = await res.json()
    if (data.success && data.series) {
      priceHistory.value = data.series
      if (data.series.length >= 2) {
        const latest = data.series[data.series.length - 1]
        const prev = data.series[data.series.length - 2]
        currentPrice.value = latest.close
        priceChange.value = latest.close - prev.close
        priceChangePercent.value = ((latest.close - prev.close) / prev.close) * 100
      }
    }
  } catch (err) {
    console.error('Failed to fetch price data:', err)
  }
}

async function fetchForecastData() {
  try {
    const horizon = horizons.find(h => h.key === activeHorizon.value)
    const res = await fetch(`${API_BASE}/api/zl/forecast?horizon=${horizon.days}`)
    const data = await res.json()
    if (data.success) {
      forecastData.value = {
        p10: data.p10 || [],
        p50: data.p50 || [],
        p90: data.p90 || []
      }
    }
  } catch (err) {
    console.error('Failed to fetch forecast:', err)
  }
}

async function fetchSpecialistData() {
  try {
    const res = await fetch(`${API_BASE}/api/drivers`)
    const data = await res.json()
    if (data.success && data.drivers) {
      data.drivers.forEach(d => {
        const spec = specialists.value.find(s => s.id === d.id)
        if (spec) {
          spec.signal = d.signal || 0
          spec.direction = d.direction || 'neutral'
          spec.history = d.history || []
        }
      })
    }
  } catch (err) {
    console.error('Failed to fetch drivers:', err)
  }
}

function renderHeroChart() {
  if (!heroChartRef.value) return
  if (heroChart) {
    heroChart.remove()
    heroChart = null
  }

  const chartHeight = Math.max(480, window.innerHeight * 0.55)

  heroChart = createChart(heroChartRef.value, {
    width: heroChartRef.value.clientWidth,
    height: chartHeight,
    layout: {
      background: { color: 'transparent' },
      textColor: '#787B86',
      fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
      attributionLogo: false
    },
    grid: {
      vertLines: { color: 'rgba(42, 46, 57, 0.5)', style: 1 },
      horzLines: { color: 'rgba(42, 46, 57, 0.5)', style: 1 }
    },
    rightPriceScale: {
      borderVisible: false,
      scaleMargins: { top: 0.1, bottom: 0.1 },
      textColor: '#787B86'
    },
    leftPriceScale: { visible: false },
    timeScale: {
      borderVisible: false,
      rightOffset: 40,
      barSpacing: 12,
      minBarSpacing: 6,
      textColor: '#787B86'
    },
    crosshair: {
      mode: 1,
      vertLine: {
        color: 'rgba(42, 46, 57, 0.8)',
        width: 1,
        style: 3,
        labelBackgroundColor: '#2A2E39'
      },
      horzLine: {
        color: 'rgba(42, 46, 57, 0.8)',
        width: 1,
        style: 3,
        labelBackgroundColor: '#2A2E39'
      }
    },
    handleScale: false,
    handleScroll: false
  })

  // Main price line with gradient fill - TradingView neon cyan
  const priceSeries = heroChart.addSeries(AreaSeries, {
    topColor: 'rgba(41, 98, 255, 0.25)',
    bottomColor: 'rgba(41, 98, 255, 0.0)',
    lineColor: '#2962FF',
    lineWidth: 2,
    priceScaleId: 'right',
    lastValueVisible: false,
    priceLineVisible: false
  })

  // P90 ceiling - thin dotted line, no fill (subtle uncertainty indicator)
  const p90Series = heroChart.addSeries(LineSeries, {
    color: 'rgba(255, 82, 82, 0.5)',
    lineWidth: 1,
    lineStyle: 3, // Dotted
    priceScaleId: 'right',
    lastValueVisible: false,
    priceLineVisible: false
  })

  // P10 floor - thin dotted line, no fill
  const p10Series = heroChart.addSeries(LineSeries, {
    color: 'rgba(0, 230, 118, 0.5)',
    lineWidth: 1,
    lineStyle: 3, // Dotted
    priceScaleId: 'right',
    lastValueVisible: false,
    priceLineVisible: false
  })

  // P50 median - subtle dashed, muted color
  const p50Series = heroChart.addSeries(LineSeries, {
    color: 'rgba(120, 123, 134, 0.6)',
    lineWidth: 1,
    lineStyle: 2, // Dashed
    priceScaleId: 'right',
    lastValueVisible: false,
    priceLineVisible: false
  })

  if (priceHistory.value.length > 0) {
    const historical = priceHistory.value.map(d => ({
      time: d.time,
      value: d.close
    }))
    priceSeries.setData(historical)
  }

  if (forecastData.value.p50.length > 0) {
    p10Series.setData(forecastData.value.p10)
    p50Series.setData(forecastData.value.p50)
    p90Series.setData(forecastData.value.p90)
  }

  heroChart.timeScale().fitContent()
}

function renderSpecialistCharts() {
  specialists.value.forEach(spec => {
    const container = specChartRefs.value[spec.id]
    if (!container) return

    if (specCharts[spec.id]) {
      specCharts[spec.id].remove()
      specCharts[spec.id] = null
    }

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 40,
      layout: {
        background: { color: 'transparent' },
        textColor: 'transparent',
        attributionLogo: false
      },
      grid: {
        vertLines: { visible: false },
        horzLines: { visible: false }
      },
      rightPriceScale: { visible: false },
      leftPriceScale: { visible: false },
      timeScale: { visible: false },
      crosshair: {
        vertLine: { visible: false },
        horzLine: { visible: false }
      },
      handleScale: false,
      handleScroll: false
    })

    // Gradient fills with neon colors
    let lineColor, topColor
    if (spec.signal > 0.01) {
      lineColor = '#00E676'
      topColor = 'rgba(0, 230, 118, 0.35)'
    } else if (spec.signal < -0.01) {
      lineColor = '#FF5252'
      topColor = 'rgba(255, 82, 82, 0.35)'
    } else {
      lineColor = '#787B86'
      topColor = 'rgba(120, 123, 134, 0.2)'
    }

    const series = chart.addSeries(AreaSeries, {
      topColor: topColor,
      bottomColor: 'transparent',
      lineColor: lineColor,
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false
    })

    if (spec.history && spec.history.length > 0) {
      series.setData(spec.history)
    } else {
      const data = []
      const baseValue = 0
      const today = new Date()
      for (let i = 30; i >= 0; i--) {
        const d = new Date(today)
        d.setDate(d.getDate() - i)
        const noise = (Math.random() - 0.5) * 0.02
        const trend = spec.signal * (30 - i) / 30
        data.push({
          time: d.toISOString().split('T')[0],
          value: baseValue + trend + noise
        })
      }
      series.setData(data)
    }

    chart.timeScale().fitContent()
    specCharts[spec.id] = chart
  })
}

function handleResize() {
  if (heroChart && heroChartRef.value) {
    heroChart.applyOptions({
      width: heroChartRef.value.clientWidth,
      height: Math.max(480, window.innerHeight * 0.55)
    })
    heroChart.timeScale().fitContent()
  }
  specialists.value.forEach(spec => {
    const container = specChartRefs.value[spec.id]
    if (container && specCharts[spec.id]) {
      specCharts[spec.id].applyOptions({ width: container.clientWidth })
      specCharts[spec.id].timeScale().fitContent()
    }
  })
}

async function checkLogoExists() {
  try {
    const res = await fetch('/zinc-logo.png', { method: 'HEAD' })
    if (res.ok) logoUrl.value = '/zinc-logo.png'
  } catch {
    logoUrl.value = null
  }
}

async function fetchAllData() {
  await Promise.all([fetchPriceData(), fetchForecastData(), fetchSpecialistData()])
  await nextTick()
  renderHeroChart()
  renderSpecialistCharts()
}

onMounted(() => {
  checkLogoExists()
  fetchAllData()
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
  if (heroChart) { heroChart.remove(); heroChart = null }
  Object.values(specCharts).forEach(chart => { if (chart) chart.remove() })
})

watch(activeHorizon, () => fetchAllData())
</script>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

.dashboard {
  min-height: 100vh;
  background: #131722;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* HERO SECTION */
.hero {
  padding: 0.75rem 0 1.5rem;
}

.ticker-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
  padding: 0 2rem;
}

.ticker-info {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}

.ticker-symbol {
  font-size: 1.75rem;
  font-weight: 700;
  color: #D1D4DC;
}

.ticker-name {
  font-size: 0.8125rem;
  color: #787B86;
}

.ticker-price {
  font-size: 1.5rem;
  font-weight: 600;
  margin-left: 1rem;
}

.ticker-price.up { color: #00E676; }
.ticker-price.down { color: #FF5252; }

.ticker-change {
  font-size: 0.8125rem;
  font-weight: 500;
}

.ticker-change.up { color: #00E676; }
.ticker-change.down { color: #FF5252; }

.ticker-meta {
  text-align: right;
}

.meta-label {
  font-size: 0.6875rem;
  color: #787B86;
  display: block;
}

.meta-value {
  font-size: 0.625rem;
  color: #5D606B;
}

/* Chart Controls */
.chart-controls {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 2rem;
  margin-bottom: 1rem;
}

/* Pill-Style Segmented Controls */
.horizon-tabs {
  display: flex;
  gap: 2px;
  background: #1E222D;
  border-radius: 4px;
  padding: 2px;
}

.horizon-tabs button {
  background: transparent;
  border: none;
  color: #787B86;
  padding: 0.375rem 0.875rem;
  font-size: 0.6875rem;
  font-weight: 600;
  font-family: inherit;
  border-radius: 3px;
  cursor: pointer;
  transition: all 0.15s;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.horizon-tabs button:hover {
  color: #B2B5BE;
  background: rgba(255, 255, 255, 0.05);
}

.horizon-tabs button.active {
  background: #2962FF;
  color: #FFFFFF;
}

/* Probability Legend */
.probability-legend {
  display: flex;
  gap: 1.5rem;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.625rem;
  color: #787B86;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.legend-item.p90 .legend-dot { background: rgba(255, 82, 82, 0.6); }
.legend-item.p50 .legend-dot { background: #787B86; }
.legend-item.p10 .legend-dot { background: rgba(0, 230, 118, 0.6); }

/* Hero Chart Wrapper */
.hero-chart-wrapper {
  position: relative;
  background: #131722;
  border: 1px solid #2A2E39;
  border-radius: 8px;
  margin: 0 2rem;
  overflow: hidden;
}

/* Massive ticker watermark */
.ticker-watermark {
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  font-size: 12rem;
  font-weight: 800;
  color: #1B1F2A;
  pointer-events: none;
  z-index: 0;
  letter-spacing: 0.1em;
}

/* Logo Watermark */
.chart-watermark {
  position: absolute;
  bottom: 1rem;
  right: 1rem;
  z-index: 0;
  pointer-events: none;
  opacity: 0.06;
}

.watermark-logo {
  width: 120px;
  height: auto;
}

.hero-chart {
  width: 100%;
  min-height: 480px;
  position: relative;
  z-index: 1;
}

/* Current Price Tag with Pulse */
.current-price-tag {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  padding: 0.375rem 0.75rem;
  border-radius: 4px 0 0 4px;
  font-size: 0.75rem;
  font-weight: 600;
  font-family: 'SF Mono', 'Monaco', monospace;
  z-index: 10;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.current-price-tag.up {
  background: #00E676;
  color: #131722;
}

.current-price-tag.down {
  background: #FF5252;
  color: #131722;
}

.price-pulse {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.5; transform: scale(1.2); }
}

/* Probability Bands Overlay */
.prob-bands {
  position: absolute;
  right: 80px;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  gap: 2rem;
  pointer-events: none;
  z-index: 2;
}

.prob-band {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.band-value {
  font-size: 0.75rem;
  font-weight: 600;
  font-family: 'SF Mono', 'Monaco', monospace;
}

.band-label {
  font-size: 0.5rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: #5D606B;
}

.p90-label .band-value { color: rgba(255, 82, 82, 0.7); }
.p50-label .band-value { color: #787B86; }
.p10-label .band-value { color: rgba(0, 230, 118, 0.7); }

/* SPECIALISTS SECTION */
.specialists-section {
  padding: 0 2rem 2rem;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #2A2E39;
}

.section-header h2 {
  font-size: 0.75rem;
  font-weight: 700;
  letter-spacing: 0.1em;
  color: #D1D4DC;
}

.section-meta {
  font-size: 0.625rem;
  color: #5D606B;
}

.specialists-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: #2A2E39;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid #2A2E39;
}

/* POSTURE CARD */
.posture-card {
  grid-column: span 2;
  background: #1E222D;
  padding: 0;
  display: flex;
  flex-direction: column;
  border-top: 2px solid transparent;
}

/* Top Accent Border by Posture */
.posture-card.bullish-accent,
.posture-card.strong-bullish-accent { border-top-color: #00E676; }
.posture-card.bearish-accent,
.posture-card.strong-bearish-accent { border-top-color: #FF5252; }
.posture-card.neutral-accent { border-top-color: #363A45; }

/* Posture Header Row */
.posture-header-row {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 1rem 1.25rem 0.75rem;
}

.posture-header-left {}

.posture-title {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: #E5E7EB;
  display: block;
}

.posture-subtitle {
  font-size: 0.5625rem;
  color: #787B86;
  margin-top: 0.125rem;
  display: block;
}

/* Large status badge for posture */
.status-badge.large {
  font-size: 0.6875rem;
  padding: 0.375rem 0.75rem;
}

/* Posture Content */
.posture-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1.25rem 1rem;
  gap: 2rem;
}

.posture-meter-container {
  flex: 1;
  max-width: 400px;
}

.posture-meter {
  position: relative;
  height: 8px;
  margin-bottom: 0.5rem;
}

.meter-track {
  display: flex;
  height: 100%;
  border-radius: 4px;
  overflow: hidden;
}

.meter-segment { flex: 1; }
.meter-segment.sell { background: linear-gradient(to right, #FF5252, #FF8A80); }
.meter-segment.neutral { background: #363A45; }
.meter-segment.buy { background: linear-gradient(to right, #69F0AE, #00E676); }

.meter-indicator {
  position: absolute;
  top: -4px;
  width: 4px;
  height: 16px;
  background: #D1D4DC;
  border-radius: 2px;
  transform: translateX(-50%);
  box-shadow: 0 0 8px rgba(255,255,255,0.3);
}

.meter-labels {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.75rem;
}

.meter-label {
  font-size: 0.5625rem;
  color: #5D606B;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.meter-label.sell { color: #FF5252; }
.meter-label.buy { color: #00E676; }

.posture-counts {
  display: flex;
  gap: 2rem;
  min-width: 180px;
  justify-content: flex-end;
}

.count-item { text-align: center; }

.count-label {
  font-size: 0.5625rem;
  color: #5D606B;
  display: block;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.count-value {
  font-size: 1.25rem;
  font-weight: 600;
}

.count-item.bearish .count-value { color: #FF5252; }
.count-item.neutral .count-value { color: #787B86; }
.count-item.bullish .count-value { color: #00E676; }

/* Specialist Cards - Dashboard Widget Style */
.specialist-card {
  display: flex;
  flex-direction: column;
  background: #1E222D;
  padding: 0;
  transition: all 0.15s;
  position: relative;
  border-top: 2px solid transparent;
}

/* Top Accent Border by Signal */
.specialist-card.bullish-accent { border-top-color: #00E676; }
.specialist-card.bearish-accent { border-top-color: #FF5252; }
.specialist-card.neutral-accent { border-top-color: #363A45; }

.specialist-card:hover {
  background: #252930;
}

/* Card Header - Compact Toolbar Style */
.spec-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  padding: 0.875rem 1rem 0.5rem;
  gap: 0.5rem;
}

.spec-header-left {
  flex: 1;
  min-width: 0;
}

.spec-header-right {
  flex-shrink: 0;
}

.spec-name {
  font-size: 0.75rem;
  font-weight: 600;
  color: #E5E7EB;
  display: block;
  letter-spacing: 0.02em;
}

.spec-description {
  font-size: 0.5625rem;
  color: #787B86;
  margin-top: 0.125rem;
  display: block;
}

/* Status Badge - TradingView Style */
.status-badge {
  display: inline-block;
  font-size: 0.5625rem;
  font-weight: 700;
  letter-spacing: 0.05em;
  padding: 0.25rem 0.5rem;
  border-radius: 3px;
  text-transform: uppercase;
  white-space: nowrap;
}

.status-badge.bullish {
  color: #00E676;
  background: rgba(0, 230, 118, 0.15);
}

.status-badge.bearish {
  color: #FF5252;
  background: rgba(255, 82, 82, 0.15);
}

.status-badge.neutral {
  color: #787B86;
  background: rgba(120, 123, 134, 0.15);
}

/* Mini Chart */
.spec-mini-chart {
  height: 44px;
  padding: 0 1rem;
}

/* Signal Row - Bottom of Card */
.spec-signal-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem 0.875rem;
  border-top: 1px solid rgba(42, 46, 57, 0.5);
  margin-top: auto;
}

/* Signal Meter */
.spec-meter {
  width: 64px;
  height: 4px;
  position: relative;
  flex-shrink: 0;
}

.spec-meter-track {
  width: 100%;
  height: 100%;
  background: #2A2E39;
  border-radius: 2px;
  overflow: hidden;
  position: relative;
}

.spec-meter-fill {
  position: absolute;
  top: 0;
  height: 100%;
  border-radius: 2px;
}

.spec-meter-fill.bullish { background: #00E676; }
.spec-meter-fill.bearish { background: #FF5252; }
.spec-meter-fill.neutral { background: #787B86; }

.spec-meter-center {
  position: absolute;
  left: 50%;
  top: -1px;
  width: 1px;
  height: calc(100% + 2px);
  background: #363A45;
  transform: translateX(-50%);
}

/* Signal Value */
.signal-value {
  font-size: 0.8125rem;
  font-weight: 600;
  font-family: 'SF Mono', 'Monaco', monospace;
}

.signal-value.bullish { color: #00E676; }
.signal-value.bearish { color: #FF5252; }
.signal-value.neutral { color: #787B86; }

/* Responsive */
@media (max-width: 900px) {
  .specialists-grid { grid-template-columns: 1fr; }
  .posture-card {
    grid-column: span 1;
    flex-direction: column;
    align-items: stretch;
    gap: 1rem;
  }
  .posture-header { text-align: center; }
  .posture-meter-container { max-width: none; }
  .posture-counts { justify-content: center; }
  .ticker-header, .chart-controls { padding: 0 1rem; }
  .hero-chart-wrapper { margin: 0 1rem; }
  .specialists-section { padding: 0 1rem 1rem; }
  .probability-legend, .prob-bands { display: none; }
  .ticker-watermark { font-size: 6rem; }
}
</style>
