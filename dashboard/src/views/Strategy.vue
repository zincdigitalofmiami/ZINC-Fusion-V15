<template>
  <div class="strategy-page">
    <header class="page-header">
      <h1 class="page-title">Procurement Strategy</h1>
      <p class="page-description">Scenario analysis | Risk metrics | Opportunity windows</p>
    </header>

    <!-- Strategy Overview -->
    <div class="grid grid-4">
      <div class="card kpi">
        <div class="kpi-value" :class="postureClass">{{ currentPosture }}</div>
        <div class="kpi-label">Current Posture</div>
      </div>
      <div class="card kpi">
        <div class="kpi-value neutral">{{ formatPercent(varP95) }}</div>
        <div class="kpi-label">VaR (95%)</div>
      </div>
      <div class="card kpi">
        <div class="kpi-value" :class="cvarClass">{{ formatPercent(cvarP95) }}</div>
        <div class="kpi-label">CVaR (95%)</div>
      </div>
      <div class="card kpi">
        <div class="kpi-value positive">{{ activeOpportunities }}</div>
        <div class="kpi-label">Active Opportunities</div>
      </div>
    </div>

    <!-- Risk Distribution Chart -->
    <LWChart
      title="Return Distribution (Monte Carlo 10K Simulations)"
      :data="distributionData"
      type="histogram"
      :height="300"
      :seriesOptions="{
        color: 'rgba(33, 150, 243, 0.7)',
      }"
    />

    <!-- Scenario Analysis -->
    <div class="grid grid-2" style="margin-top: 16px;">
      <div class="card">
        <div class="card-header">
          <span class="card-title">Scenario Analysis (Monte Carlo)</span>
        </div>
        <div class="scenario-table">
          <div class="table-header">
            <span class="col-scenario">Scenario</span>
            <span class="col-prob">Probability</span>
            <span class="col-return">Expected Return</span>
            <span class="col-range">P10-P90 Range</span>
          </div>
          <div v-for="scenario in scenarios" :key="scenario.name" class="table-row">
            <span class="col-scenario">
              <span class="scenario-dot" :class="scenario.class"></span>
              {{ scenario.name }}
            </span>
            <span class="col-prob">{{ formatPercent(scenario.probability) }}</span>
            <span class="col-return" :class="scenario.expected > 0 ? 'positive' : 'negative'">
              {{ scenario.expected > 0 ? '+' : '' }}{{ scenario.expected.toFixed(2) }}%
            </span>
            <span class="col-range">
              {{ scenario.p10.toFixed(1) }}% to {{ scenario.p90.toFixed(1) }}%
            </span>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">Risk Metrics by Horizon</span>
        </div>
        <div class="risk-matrix">
          <div class="matrix-header">
            <span class="col-horizon">Horizon</span>
            <span class="col-metric">VaR (95%)</span>
            <span class="col-metric">CVaR (95%)</span>
            <span class="col-metric">Max DD</span>
            <span class="col-metric">Sharpe</span>
          </div>
          <div v-for="horizon in riskByHorizon" :key="horizon.name" class="matrix-row">
            <span class="col-horizon">{{ horizon.name }}</span>
            <span class="col-metric negative">{{ horizon.var.toFixed(2) }}%</span>
            <span class="col-metric negative">{{ horizon.cvar.toFixed(2) }}%</span>
            <span class="col-metric negative">{{ horizon.maxDD.toFixed(2) }}%</span>
            <span class="col-metric" :class="horizon.sharpe > 1 ? 'positive' : 'neutral'">
              {{ horizon.sharpe.toFixed(2) }}
            </span>
          </div>
        </div>
      </div>
    </div>

    <!-- Opportunity Windows -->
    <div class="card" style="margin-top: 16px;">
      <div class="card-header">
        <span class="card-title">Opportunity Windows</span>
        <div class="header-actions">
          <span class="status-indicator">
            <span class="status-dot live"></span>
            Live Analysis
          </span>
        </div>
      </div>
      <div class="opportunity-grid">
        <div 
          v-for="opp in opportunities" 
          :key="opp.id" 
          class="opportunity-card"
          :class="opp.strength"
        >
          <div class="opp-header">
            <span class="opp-type">{{ opp.type }}</span>
            <span class="opp-horizon">{{ opp.horizon }}</span>
          </div>
          <div class="opp-signal">
            <span class="signal-label">Signal Strength</span>
            <div class="signal-bar">
              <div class="signal-fill" :style="{ width: opp.signalStrength * 100 + '%' }"></div>
            </div>
            <span class="signal-value">{{ formatPercent(opp.signalStrength) }}</span>
          </div>
          <div class="opp-metrics">
            <div class="metric">
              <span class="metric-label">Probability</span>
              <span class="metric-value">{{ formatPercent(opp.probability) }}</span>
            </div>
            <div class="metric">
              <span class="metric-label">Expected Move</span>
              <span class="metric-value" :class="opp.expectedMove > 0 ? 'positive' : 'negative'">
                {{ opp.expectedMove > 0 ? '+' : '' }}{{ opp.expectedMove.toFixed(2) }}%
              </span>
            </div>
            <div class="metric">
              <span class="metric-label">Confidence</span>
              <span class="metric-value">{{ opp.confidence }}</span>
            </div>
          </div>
          <div class="opp-drivers">
            <span class="drivers-label">Key Drivers:</span>
            <span v-for="driver in opp.drivers" :key="driver" class="badge badge-blue">
              {{ driver }}
            </span>
          </div>
          <div class="opp-window">
            <span class="window-label">Window:</span>
            <span class="window-dates">{{ opp.windowStart }} - {{ opp.windowEnd }}</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Driver Attribution -->
    <div class="card" style="margin-top: 16px;">
      <div class="card-header">
        <span class="card-title">Driver Attribution (Current Week)</span>
      </div>
      <div class="attribution-chart">
        <div v-for="driver in driverAttribution" :key="driver.name" class="attribution-row">
          <span class="attr-name">{{ driver.name }}</span>
          <div class="attr-bar-container">
            <div 
              class="attr-bar" 
              :class="driver.contribution > 0 ? 'positive' : 'negative'"
              :style="{ width: Math.abs(driver.contribution) * 5 + '%' }"
            ></div>
          </div>
          <span class="attr-value" :class="driver.contribution > 0 ? 'positive' : 'negative'">
            {{ driver.contribution > 0 ? '+' : '' }}{{ driver.contribution.toFixed(2) }}%
          </span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import LWChart from '../components/charts/LWChart.vue'

// Strategy data - populated from API
const currentPosture = ref(null)
const varP95 = ref(null)
const cvarP95 = ref(null)
const activeOpportunities = ref(null)

const distributionData = ref([])

const postureClass = computed(() => {
  const map = {
    'Defensive': 'negative',
    'Opportunistic': 'positive',
    'Neutral': 'neutral',
    'Aggressive': 'positive',
  }
  return map[currentPosture.value] || 'neutral'
})

const cvarClass = computed(() => cvarP95.value < -0.10 ? 'negative' : 'neutral')

const scenarios = ref([])
const riskByHorizon = ref([])
const opportunities = ref([])
const driverAttribution = ref([])

function formatPercent(val) {
  return (val * 100).toFixed(1) + '%'
}

async function fetchStrategyData() {
  try {
    const [postureRes, scenariosRes, riskRes, oppsRes] = await Promise.all([
      fetch('/api/strategy/posture'),
      fetch('/api/strategy/scenarios'),
      fetch('/api/strategy/risk'),
      fetch('/api/strategy/opportunities'),
    ])
    
    if (postureRes.ok) {
      const data = await postureRes.json()
      if (data.posture) currentPosture.value = data.posture
      if (data.var != null) varP95.value = data.var
      if (data.cvar != null) cvarP95.value = data.cvar
      if (data.activeOpportunities != null) activeOpportunities.value = data.activeOpportunities
      if (data.distribution) distributionData.value = data.distribution
    }
    
    if (scenariosRes.ok) {
      const data = await scenariosRes.json()
      if (data.scenarios) scenarios.value = data.scenarios
    }
    
    if (riskRes.ok) {
      const data = await riskRes.json()
      if (data.riskByHorizon) riskByHorizon.value = data.riskByHorizon
      if (data.driverAttribution) driverAttribution.value = data.driverAttribution
    }
    
    if (oppsRes.ok) {
      const data = await oppsRes.json()
      if (data.opportunities) opportunities.value = data.opportunities
    }
  } catch (err) {
    console.error('Failed to fetch strategy data:', err)
  }
}

onMounted(() => {
  fetchStrategyData()
})
</script>

<style scoped>
.scenario-table, .risk-matrix {
  border: 1px solid var(--tv-border);
  border-radius: 6px;
  overflow: hidden;
}

.table-header, .matrix-header {
  display: grid;
  padding: 12px 16px;
  background: var(--tv-bg-tertiary);
  font-size: 12px;
  font-weight: 600;
  color: var(--tv-text-muted);
  text-transform: uppercase;
}

.table-header { grid-template-columns: 2fr 1fr 1fr 1.5fr; }
.matrix-header { grid-template-columns: 1fr 1fr 1fr 1fr 1fr; }

.table-row, .matrix-row {
  display: grid;
  padding: 12px 16px;
  border-top: 1px solid var(--tv-border);
  font-size: 13px;
}

.table-row { grid-template-columns: 2fr 1fr 1fr 1.5fr; }
.matrix-row { grid-template-columns: 1fr 1fr 1fr 1fr 1fr; }

.col-scenario { display: flex; align-items: center; gap: 8px; }
.scenario-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.scenario-dot.base { background: var(--tv-blue); }
.scenario-dot.bull { background: var(--tv-green); }
.scenario-dot.bear { background: var(--tv-red); }
.scenario-dot.tail { background: var(--tv-orange); }

.opportunity-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

.opportunity-card {
  padding: 20px;
  background: var(--tv-bg-primary);
  border-radius: 8px;
  border: 2px solid var(--tv-border);
}

.opportunity-card.strong {
  border-color: var(--tv-green);
  background: rgba(38, 166, 154, 0.05);
}

.opportunity-card.moderate {
  border-color: var(--tv-blue);
  background: rgba(33, 150, 243, 0.05);
}

.opp-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.opp-type {
  font-weight: 700;
  font-size: 15px;
}

.opp-horizon {
  font-size: 12px;
  padding: 4px 10px;
  background: var(--tv-bg-tertiary);
  border-radius: 4px;
  color: var(--tv-text-muted);
}

.opp-signal {
  margin-bottom: 16px;
}

.signal-label {
  font-size: 11px;
  color: var(--tv-text-muted);
  text-transform: uppercase;
  margin-bottom: 4px;
  display: block;
}

.signal-bar {
  height: 8px;
  background: var(--tv-bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 4px;
}

.signal-fill {
  height: 100%;
  background: linear-gradient(90deg, var(--tv-blue), var(--tv-green));
  border-radius: 4px;
}

.signal-value {
  font-size: 13px;
  font-weight: 600;
}

.opp-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}

.metric {
  text-align: center;
}

.metric-label {
  display: block;
  font-size: 10px;
  color: var(--tv-text-muted);
  text-transform: uppercase;
  margin-bottom: 4px;
}

.metric-value {
  font-size: 14px;
  font-weight: 600;
}

.opp-drivers {
  margin-bottom: 12px;
  font-size: 12px;
}

.drivers-label {
  color: var(--tv-text-muted);
  margin-right: 8px;
}

.opp-window {
  padding-top: 12px;
  border-top: 1px solid var(--tv-border);
  font-size: 12px;
}

.window-label {
  color: var(--tv-text-muted);
  margin-right: 8px;
}

.window-dates {
  font-weight: 600;
}

.status-indicator {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--tv-text-muted);
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.status-dot.live {
  background: var(--tv-green);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.attribution-chart {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.attribution-row {
  display: grid;
  grid-template-columns: 140px 1fr 80px;
  align-items: center;
  gap: 16px;
}

.attr-name {
  font-size: 13px;
  font-weight: 500;
}

.attr-bar-container {
  height: 20px;
  background: var(--tv-bg-tertiary);
  border-radius: 4px;
  overflow: hidden;
}

.attr-bar {
  height: 100%;
  border-radius: 4px;
}

.attr-bar.positive { background: var(--tv-green); }
.attr-bar.negative { background: var(--tv-red); }

.attr-value {
  text-align: right;
  font-weight: 600;
  font-size: 13px;
}

.positive { color: var(--tv-green); }
.negative { color: var(--tv-red); }
.neutral { color: var(--tv-text-primary); }
</style>
