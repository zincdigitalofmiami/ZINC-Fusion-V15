<template>
  <div class="legislation-page">
    <header class="page-header">
      <h1 class="page-title">Legislation & Policy</h1>
      <p class="page-description">Regulatory tracking | Impact assessment | Policy probability shifts</p>
    </header>

    <!-- Policy Impact Summary -->
    <div class="grid grid-4">
      <div class="card kpi">
        <div class="kpi-value" :class="activeRegsClass">{{ activeRegulations }}</div>
        <div class="kpi-label">Active Regulations</div>
      </div>
      <div class="card kpi">
        <div class="kpi-value positive">{{ pendingProposals }}</div>
        <div class="kpi-label">Pending Proposals</div>
      </div>
      <div class="card kpi">
        <div class="kpi-value neutral">{{ formatPercent(avgImpactProb) }}</div>
        <div class="kpi-label">Avg Impact Probability</div>
      </div>
      <div class="card kpi">
        <div class="kpi-value" :class="netPolicyImpactClass">
          {{ netPolicyImpact > 0 ? '+' : '' }}{{ netPolicyImpact.toFixed(1) }}%
        </div>
        <div class="kpi-label">Net Policy Impact (90D)</div>
      </div>
    </div>

    <!-- Policy Timeline -->
    <div class="card" style="margin-top: 16px;">
      <div class="card-header">
        <span class="card-title">Policy Timeline</span>
        <select v-model="timelineFilter" class="select-input">
          <option value="all">All Categories</option>
          <option value="tariff">Tariff</option>
          <option value="biofuel">Biofuel</option>
          <option value="trade">Trade</option>
          <option value="environment">Environmental</option>
        </select>
      </div>
      <div class="timeline">
        <div 
          v-for="event in filteredTimeline" 
          :key="event.id" 
          class="timeline-item"
          :class="event.status"
        >
          <div class="timeline-date">
            <span class="date-day">{{ formatDay(event.date) }}</span>
            <span class="date-month">{{ formatMonth(event.date) }}</span>
          </div>
          <div class="timeline-marker" :class="event.status"></div>
          <div class="timeline-content">
            <div class="timeline-header">
              <span class="timeline-title">{{ event.title }}</span>
              <span class="badge" :class="getStatusBadge(event.status)">{{ event.status }}</span>
            </div>
            <p class="timeline-description">{{ event.description }}</p>
            <div class="timeline-meta">
              <div class="meta-item">
                <span class="meta-label">Category:</span>
                <span class="badge badge-blue">{{ event.category }}</span>
              </div>
              <div class="meta-item">
                <span class="meta-label">Impact Probability:</span>
                <span :class="event.impactProb > 0.6 ? 'positive' : 'neutral'">
                  {{ formatPercent(event.impactProb) }}
                </span>
              </div>
              <div class="meta-item">
                <span class="meta-label">Price Effect:</span>
                <span :class="event.priceEffect > 0 ? 'positive' : 'negative'">
                  {{ event.priceEffect > 0 ? '+' : '' }}{{ event.priceEffect.toFixed(2) }}%
                </span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Policy Categories -->
    <div class="grid grid-2" style="margin-top: 16px;">
      <!-- Tariff Watch -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Tariff Watch</span>
        </div>
        <div class="policy-list">
          <div v-for="tariff in tariffWatch" :key="tariff.id" class="policy-item">
            <div class="policy-name">{{ tariff.name }}</div>
            <div class="policy-details">
              <span class="detail-item">
                <span class="detail-label">Current Rate:</span>
                {{ tariff.currentRate }}%
              </span>
              <span class="detail-item">
                <span class="detail-label">Proposed:</span>
                {{ tariff.proposedRate }}%
              </span>
              <span class="detail-item">
                <span class="detail-label">Prob:</span>
                <span :class="tariff.probability > 0.5 ? 'positive' : 'neutral'">
                  {{ formatPercent(tariff.probability) }}
                </span>
              </span>
            </div>
            <div class="prob-bar">
              <div 
                class="prob-fill" 
                :class="tariff.probability > 0.5 ? 'high' : 'medium'"
                :style="{ width: tariff.probability * 100 + '%' }"
              ></div>
            </div>
          </div>
        </div>
      </div>

      <!-- Biofuel Mandates -->
      <div class="card">
        <div class="card-header">
          <span class="card-title">Biofuel Mandates</span>
        </div>
        <div class="policy-list">
          <div v-for="mandate in biofuelMandates" :key="mandate.id" class="policy-item">
            <div class="policy-name">{{ mandate.name }}</div>
            <div class="policy-details">
              <span class="detail-item">
                <span class="detail-label">Current:</span>
                {{ mandate.currentVolume }}B gal
              </span>
              <span class="detail-item">
                <span class="detail-label">Target:</span>
                {{ mandate.targetVolume }}B gal
              </span>
              <span class="detail-item">
                <span class="detail-label">Effective:</span>
                {{ mandate.effectiveDate }}
              </span>
            </div>
            <div class="mandate-impact">
              <span class="impact-label">Demand Impact:</span>
              <span class="positive">+{{ mandate.demandImpact }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Regulatory Calendar -->
    <div class="card" style="margin-top: 16px;">
      <div class="card-header">
        <span class="card-title">Regulatory Calendar</span>
      </div>
      <div class="calendar-grid">
        <div v-for="event in upcomingEvents" :key="event.id" class="calendar-item">
          <div class="calendar-date">
            <span class="cal-day">{{ formatCalDay(event.date) }}</span>
            <span class="cal-month">{{ formatCalMonth(event.date) }}</span>
          </div>
          <div class="calendar-content">
            <div class="calendar-title">{{ event.title }}</div>
            <div class="calendar-agency">{{ event.agency }}</div>
            <div class="calendar-impact">
              <span class="badge" :class="getImpactBadge(event.impact)">
                {{ event.impact }} Impact
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

// Summary KPIs - populated from API
const activePolicies = ref(null)
const pendingChanges = ref(null)
const avgImpactProb = ref(null)
const netPolicyImpact = ref(null)
const upcomingDeadlines = ref(null)

const timelineFilter = ref('all')

const activeRegsClass = computed(() => 
  activeRegulations.value > 20 ? 'neutral' : 'positive'
)

const netPolicyImpactClass = computed(() =>
  netPolicyImpact.value > 0 ? 'positive' : 'negative'
)

// Policy data - populated from API
const policyTimeline = ref([])

const filteredTimeline = computed(() => {
  if (timelineFilter.value === 'all') return policyTimeline.value
  return policyTimeline.value.filter(e => e.category === timelineFilter.value)
})

const tariffWatch = ref([])
const biofuelMandates = ref([])
const upcomingEvents = ref([])

function formatPercent(val) {
  return (val * 100).toFixed(1) + '%'
}

function formatDay(date) {
  return new Date(date).getDate()
}

function formatMonth(date) {
  return new Date(date).toLocaleDateString('en-US', { month: 'short' })
}

function formatCalDay(date) {
  return new Date(date).getDate()
}

function formatCalMonth(date) {
  return new Date(date).toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

function getStatusBadge(status) {
  const map = {
    upcoming: 'badge-blue',
    active: 'badge-orange',
    completed: 'badge-green',
  }
  return map[status] || 'badge-blue'
}

function getImpactBadge(impact) {
  const map = {
    High: 'badge-red',
    Medium: 'badge-orange',
    Low: 'badge-green',
  }
  return map[impact] || 'badge-blue'
}

async function fetchLegislationData() {
  try {
    const [timelineRes, tariffsRes, mandatesRes, eventsRes, summaryRes] = await Promise.all([
      fetch('/api/legislation/timeline'),
      fetch('/api/legislation/tariffs'),
      fetch('/api/legislation/mandates'),
      fetch('/api/legislation/events'),
      fetch('/api/legislation/summary'),
    ])
    
    if (timelineRes.ok) {
      const data = await timelineRes.json()
      if (data.timeline) policyTimeline.value = data.timeline
    }
    
    if (tariffsRes.ok) {
      const data = await tariffsRes.json()
      if (data.tariffs) tariffWatch.value = data.tariffs
    }
    
    if (mandatesRes.ok) {
      const data = await mandatesRes.json()
      if (data.mandates) biofuelMandates.value = data.mandates
    }
    
    if (eventsRes.ok) {
      const data = await eventsRes.json()
      if (data.events) upcomingEvents.value = data.events
    }
    
    if (summaryRes.ok) {
      const data = await summaryRes.json()
      if (data.activeCount != null) activePolicies.value = data.activeCount
      if (data.pendingChanges != null) pendingChanges.value = data.pendingChanges
      if (data.netImpact != null) netPolicyImpact.value = data.netImpact
      if (data.upcomingDeadlines != null) upcomingDeadlines.value = data.upcomingDeadlines
    }
  } catch (err) {
    console.error('Failed to fetch legislation data:', err)
  }
}

onMounted(() => {
  fetchLegislationData()
})
</script>

<style scoped>
.timeline {
  position: relative;
  padding-left: 100px;
}

.timeline-item {
  position: relative;
  padding: 20px 0 20px 40px;
  border-left: 2px solid var(--tv-border);
}

.timeline-item:last-child {
  border-left-color: transparent;
}

.timeline-date {
  position: absolute;
  left: -100px;
  width: 80px;
  text-align: right;
  padding-right: 20px;
}

.date-day {
  display: block;
  font-size: 24px;
  font-weight: 700;
  color: var(--tv-text-primary);
}

.date-month {
  display: block;
  font-size: 12px;
  color: var(--tv-text-muted);
  text-transform: uppercase;
}

.timeline-marker {
  position: absolute;
  left: -8px;
  top: 24px;
  width: 14px;
  height: 14px;
  border-radius: 50%;
  background: var(--tv-bg-secondary);
  border: 3px solid var(--tv-blue);
}

.timeline-marker.upcoming { border-color: var(--tv-blue); }
.timeline-marker.active { border-color: var(--tv-orange); background: var(--tv-orange); }
.timeline-marker.completed { border-color: var(--tv-green); }

.timeline-content {
  background: var(--tv-bg-primary);
  border-radius: 8px;
  padding: 16px;
  border: 1px solid var(--tv-border);
}

.timeline-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.timeline-title {
  font-weight: 600;
  font-size: 15px;
}

.timeline-description {
  color: var(--tv-text-secondary);
  font-size: 13px;
  line-height: 1.5;
  margin-bottom: 12px;
}

.timeline-meta {
  display: flex;
  gap: 24px;
  padding-top: 12px;
  border-top: 1px solid var(--tv-border);
}

.meta-item {
  font-size: 13px;
}

.meta-label {
  color: var(--tv-text-muted);
  margin-right: 4px;
}

.policy-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.policy-item {
  padding: 12px;
  background: var(--tv-bg-primary);
  border-radius: 6px;
  border: 1px solid var(--tv-border);
}

.policy-name {
  font-weight: 600;
  margin-bottom: 8px;
}

.policy-details {
  display: flex;
  gap: 16px;
  font-size: 13px;
  margin-bottom: 8px;
}

.detail-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.detail-label {
  color: var(--tv-text-muted);
}

.mandate-impact {
  margin-top: 8px;
  font-size: 13px;
}

.impact-label {
  color: var(--tv-text-muted);
  margin-right: 8px;
}

.calendar-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 16px;
}

.calendar-item {
  display: flex;
  gap: 16px;
  padding: 16px;
  background: var(--tv-bg-primary);
  border-radius: 8px;
  border: 1px solid var(--tv-border);
}

.calendar-date {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-width: 60px;
  padding: 8px;
  background: var(--tv-bg-tertiary);
  border-radius: 6px;
}

.cal-day {
  font-size: 24px;
  font-weight: 700;
}

.cal-month {
  font-size: 11px;
  color: var(--tv-text-muted);
  text-transform: uppercase;
}

.calendar-content {
  flex: 1;
}

.calendar-title {
  font-weight: 600;
  margin-bottom: 4px;
}

.calendar-agency {
  font-size: 12px;
  color: var(--tv-text-muted);
  margin-bottom: 8px;
}

.select-input {
  background: var(--tv-bg-tertiary);
  border: 1px solid var(--tv-border);
  border-radius: 4px;
  padding: 6px 12px;
  color: var(--tv-text-primary);
  font-size: 13px;
}

.positive { color: var(--tv-green); }
.negative { color: var(--tv-red); }
.neutral { color: var(--tv-text-primary); }
</style>
