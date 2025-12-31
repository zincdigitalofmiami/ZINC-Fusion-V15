<template>
  <div class="chart-container">
    <div v-if="title" class="chart-header">
      <span class="chart-title">{{ title }}</span>
      <slot name="header-right" />
    </div>
    <div ref="chartContainer" class="chart-wrapper" :style="{ height: height + 'px' }"></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, watch, shallowRef } from 'vue'
import { createChart, ColorType, CrosshairMode } from 'lightweight-charts'

const props = defineProps({
  title: { type: String, default: '' },
  height: { type: Number, default: 400 },
  type: { type: String, default: 'candlestick' }, // candlestick, line, area, histogram, baseline
  data: { type: Array, required: true },
  options: { type: Object, default: () => ({}) },
  seriesOptions: { type: Object, default: () => ({}) },
  // For probability bands (P10/P50/P90)
  bandsData: { type: Object, default: null }, // { p10: [], p50: [], p90: [] }
})

const emit = defineEmits(['chartReady', 'crosshairMove'])

const chartContainer = ref(null)

// Use plain variables (not refs) for chart instances per TradingView docs
let chart = null
let mainSeries = null
let bandSeries = {}

// TradingView dark theme defaults
const defaultChartOptions = {
  layout: {
    background: { type: ColorType.Solid, color: '#131722' },
    textColor: '#d1d4dc',
    fontSize: 12,
    fontFamily: 'Inter, -apple-system, sans-serif',
  },
  grid: {
    vertLines: { color: '#1e222d' },
    horzLines: { color: '#1e222d' },
  },
  crosshair: {
    mode: CrosshairMode.Normal,
    vertLine: { color: '#758696', width: 1, style: 3, labelBackgroundColor: '#2a2e39' },
    horzLine: { color: '#758696', width: 1, style: 3, labelBackgroundColor: '#2a2e39' },
  },
  rightPriceScale: {
    borderColor: '#2a2e39',
    scaleMargins: { top: 0.1, bottom: 0.2 },
  },
  timeScale: {
    borderColor: '#2a2e39',
    timeVisible: true,
    secondsVisible: false,
  },
  handleScroll: { vertTouchDrag: false },
}

// Series type configurations
const seriesConfigs = {
  candlestick: {
    upColor: '#26a69a',
    downColor: '#ef5350',
    borderVisible: false,
    wickUpColor: '#26a69a',
    wickDownColor: '#ef5350',
  },
  line: {
    color: '#2962ff',
    lineWidth: 2,
  },
  area: {
    topColor: 'rgba(41, 98, 255, 0.4)',
    bottomColor: 'rgba(41, 98, 255, 0.0)',
    lineColor: '#2962ff',
    lineWidth: 2,
  },
  histogram: {
    color: '#26a69a',
    priceFormat: { type: 'volume' },
    priceScaleId: '',
  },
  baseline: {
    baseValue: { type: 'price', price: 0 },
    topFillColor1: 'rgba(38, 166, 154, 0.4)',
    topFillColor2: 'rgba(38, 166, 154, 0.0)',
    topLineColor: '#26a69a',
    bottomFillColor1: 'rgba(239, 83, 80, 0.0)',
    bottomFillColor2: 'rgba(239, 83, 80, 0.4)',
    bottomLineColor: '#ef5350',
  },
}

// Band colors for P10/P50/P90
const bandColors = {
  p10: { color: 'rgba(239, 83, 80, 0.3)', lineWidth: 1 },
  p50: { color: '#ff9800', lineWidth: 2 },
  p90: { color: 'rgba(38, 166, 154, 0.3)', lineWidth: 1 },
}

function getSeriesType(type) {
  const types = {
    candlestick: 'Candlestick',
    line: 'Line',
    area: 'Area',
    histogram: 'Histogram',
    baseline: 'Baseline',
  }
  return types[type] || 'Line'
}

function createSeriesInstance(chart, type, options) {
  const seriesType = getSeriesType(type)
  const defaultOpts = seriesConfigs[type] || {}
  const mergedOpts = { ...defaultOpts, ...options }
  
  // Use the new addSeries API
  const SeriesClass = {
    Candlestick: () => import('lightweight-charts').then(m => m.CandlestickSeries),
    Line: () => import('lightweight-charts').then(m => m.LineSeries),
    Area: () => import('lightweight-charts').then(m => m.AreaSeries),
    Histogram: () => import('lightweight-charts').then(m => m.HistogramSeries),
    Baseline: () => import('lightweight-charts').then(m => m.BaselineSeries),
  }
  
  // Fallback to legacy API for compatibility
  switch (type) {
    case 'candlestick':
      return chart.addCandlestickSeries(mergedOpts)
    case 'line':
      return chart.addLineSeries(mergedOpts)
    case 'area':
      return chart.addAreaSeries(mergedOpts)
    case 'histogram':
      return chart.addHistogramSeries(mergedOpts)
    case 'baseline':
      return chart.addBaselineSeries(mergedOpts)
    default:
      return chart.addLineSeries(mergedOpts)
  }
}

function initChart() {
  if (!chartContainer.value) return
  
  const mergedOptions = { ...defaultChartOptions, ...props.options }
  chart = createChart(chartContainer.value, mergedOptions)
  
  // Create main series
  mainSeries = createSeriesInstance(chart, props.type, props.seriesOptions)
  
  if (props.data?.length) {
    mainSeries.setData(props.data)
  }
  
  // Create probability bands if provided
  if (props.bandsData) {
    Object.entries(props.bandsData).forEach(([key, data]) => {
      if (data?.length && bandColors[key]) {
        bandSeries[key] = chart.addLineSeries({
          ...bandColors[key],
          priceLineVisible: false,
          lastValueVisible: false,
        })
        bandSeries[key].setData(data)
      }
    })
  }
  
  // Fit content
  chart.timeScale().fitContent()
  
  // Subscribe to crosshair move
  chart.subscribeCrosshairMove((param) => {
    emit('crosshairMove', param)
  })
  
  emit('chartReady', { chart, mainSeries, bandSeries })
}

function destroyChart() {
  if (chart) {
    chart.remove()
    chart = null
    mainSeries = null
    bandSeries = {}
  }
}

// Watch for data changes
watch(() => props.data, (newData) => {
  if (mainSeries && newData?.length) {
    mainSeries.setData(newData)
    chart?.timeScale().fitContent()
  }
}, { deep: true })

// Watch for bands data changes
watch(() => props.bandsData, (newBands) => {
  if (!chart || !newBands) return
  
  Object.entries(newBands).forEach(([key, data]) => {
    if (bandSeries[key] && data?.length) {
      bandSeries[key].setData(data)
    }
  })
}, { deep: true })

onMounted(() => {
  initChart()
})

onUnmounted(() => {
  destroyChart()
})

// Expose methods for parent component
defineExpose({
  getChart: () => chart,
  getSeries: () => mainSeries,
  fitContent: () => chart?.timeScale().fitContent(),
  update: (data) => mainSeries?.update(data),
})
</script>

<style scoped>
.chart-container {
  background: var(--tv-bg-primary);
  border: 1px solid var(--tv-border);
  border-radius: 8px;
  overflow: hidden;
}

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  border-bottom: 1px solid var(--tv-border);
  background: var(--tv-bg-secondary);
}

.chart-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--tv-text-primary);
}

.chart-wrapper {
  width: 100%;
}
</style>
