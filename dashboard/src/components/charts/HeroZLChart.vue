<script setup>
/**
 * HeroZLChart.vue
 * 
 * Full-width hero chart for ZL price with probability bands.
 * 100vw, no wrapper card, no borders.
 * The chart owns the screen.
 */

import { onMounted, onBeforeUnmount, ref, watch, computed } from 'vue'
import { 
  useLightweightChart, 
  addPriceSeries, 
  addP50Series, 
  addP10Series, 
  addP90Series,
  addShapSeries,
  updateShapColor,
  createMarkers 
} from './useLightweightChart.js'

const props = defineProps({
  series: {
    type: Object,
    required: true,
    // { price: [], p10: [], p50: [], p90: [] }
  },
  shap: {
    type: Object,
    default: null,
    // { aggregate: [], by_driver?: {} }
  },
  events: {
    type: Array,
    default: () => [],
    // [{ time, type, label, regime?, category? }]
  },
  showShap: {
    type: Boolean,
    default: false,
  },
  chartType: {
    type: String,
    default: 'candlestick', // 'candlestick' | 'line'
  },
})

const emit = defineEmits(['crosshairMove'])

const chartContainer = ref(null)
let chart = null
let priceSeries = null
let p50Series = null
let p10Series = null
let p90Series = null
let shapSeries = null

function initChart() {
  if (!chartContainer.value) return
  
  const api = useLightweightChart(chartContainer.value, {
    height: Math.round(window.innerHeight * 0.7),
  })
  chart = api.chart
  
  // Add series in correct z-order
  p10Series = addP10Series(chart)
  p90Series = addP90Series(chart)
  p50Series = addP50Series(chart)
  priceSeries = addPriceSeries(chart, props.chartType)
  shapSeries = addShapSeries(chart)
  
  // Set initial data
  updateSeriesData()
  
  // Crosshair callback
  chart.subscribeCrosshairMove((param) => {
    emit('crosshairMove', param)
  })
  
  // Resize handler
  const onResize = () => {
    if (chart && chartContainer.value) {
      chart.applyOptions({
        width: chartContainer.value.clientWidth,
        height: Math.round(window.innerHeight * 0.7),
      })
    }
  }
  window.addEventListener('resize', onResize)
}

function updateSeriesData() {
  if (!chart) return
  
  // Price series
  if (props.series.price?.length) {
    priceSeries.setData(props.series.price)
  }
  
  // Probability bands
  if (props.series.p10?.length) {
    p10Series.setData(props.series.p10)
  }
  if (props.series.p50?.length) {
    p50Series.setData(props.series.p50)
  }
  if (props.series.p90?.length) {
    p90Series.setData(props.series.p90)
  }
  
  // SHAP overlay
  if (props.shap?.aggregate?.length) {
    shapSeries.setData(props.shap.aggregate)
    const lastValue = props.shap.aggregate[props.shap.aggregate.length - 1]?.value || 0
    updateShapColor(shapSeries, lastValue)
  }
  
  // Regime/Event markers
  if (props.events?.length && priceSeries) {
    const markers = createMarkers(props.events)
    priceSeries.setMarkers(markers)
  }
  
  // Fit content
  chart.timeScale().fitContent()
}

// Watch for data changes
watch(() => props.series, () => {
  updateSeriesData()
}, { deep: true })

watch(() => props.shap, () => {
  if (props.shap?.aggregate?.length && shapSeries) {
    shapSeries.setData(props.shap.aggregate)
  }
}, { deep: true })

watch(() => props.events, () => {
  if (props.events?.length && priceSeries) {
    const markers = createMarkers(props.events)
    priceSeries.setMarkers(markers)
  }
}, { deep: true })

// Toggle SHAP visibility
watch(() => props.showShap, (visible) => {
  if (shapSeries) {
    shapSeries.applyOptions({ visible })
  }
})

onMounted(() => {
  initChart()
})

onBeforeUnmount(() => {
  if (chart) {
    chart.remove()
    chart = null
  }
})
</script>

<template>
  <section class="hero-chart">
    <div ref="chartContainer" class="chart-canvas"></div>
  </section>
</template>

<style scoped>
.hero-chart {
  width: 100vw;
  margin-left: calc(-50vw + 50%);
  background: var(--chart-bg, #0B0F14);
}

.chart-canvas {
  width: 100vw;
  height: 70vh;
  min-height: 400px;
}

/* No wrapper, no card, no shadow, no borders */
</style>
