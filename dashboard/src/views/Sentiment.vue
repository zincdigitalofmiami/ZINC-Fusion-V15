<template>
  <div class="sentiment-page">
    <header class="page-header">
      <h1 class="page-title">Sentiment Analysis</h1>
      <p class="page-description">LLM-analyzed news | Policy signals | Market impact probabilities</p>
    </header>

    <!-- Sentiment Overview -->
    <div class="grid grid-4">
      <div class="card kpi">
        <div class="kpi-value" :class="overallSentimentClass">{{ formatScore(overallSentiment) }}</div>
        <div class="kpi-label">Overall Sentiment</div>
        <div class="prob-bar">
          <div class="prob-fill" :class="overallSentimentClass" :style="{ width: sentimentBarWidth }"></div>
        </div>
      </div>
      <div class="card kpi">
        <div class="kpi-value neutral">{{ articleCount }}</div>
        <div class="kpi-label">Articles Analyzed (7D)</div>
      </div>
      <div class="card kpi">
        <div class="kpi-value" :class="policyImpactClass">{{ formatPercent(policyImpact) }}</div>
        <div class="kpi-label">Policy Impact Probability</div>
      </div>
      <div class="card kpi">
        <div class="kpi-value neutral">{{ majorEvents }}</div>
        <div class="kpi-label">Major Events Detected</div>
      </div>
    </div>

    <!-- Sentiment Time Series Chart -->
    <LWChart
      title="Sentiment Score Over Time"
      :data="sentimentSeries"
      type="area"
      :height="350"
      :seriesOptions="{ 
        topColor: 'rgba(38, 166, 154, 0.4)',
        bottomColor: 'rgba(38, 166, 154, 0.0)',
        lineColor: '#26a69a',
      }"
    />

    <!-- Policy Sentiment Breakdown -->
    <div class="grid grid-2" style="margin-top: 16px;">
      <div class="card">
        <div class="card-header">
          <span class="card-title">Policy Sentiment by Category</span>
        </div>
        <div class="policy-breakdown">
          <div v-for="policy in policySentiment" :key="policy.category" class="policy-item">
            <div class="policy-header">
              <span class="policy-icon">{{ policy.icon }}</span>
              <span class="policy-name">{{ policy.category }}</span>
              <span class="policy-score" :class="policy.sentiment > 0 ? 'positive' : 'negative'">
                {{ policy.sentiment > 0 ? '+' : '' }}{{ formatScore(policy.sentiment) }}
              </span>
            </div>
            <div class="prob-bar">
              <div 
                class="prob-fill" 
                :class="policy.sentiment > 0 ? 'high' : 'low'"
                :style="{ width: Math.abs(policy.sentiment * 50) + 50 + '%' }"
              ></div>
            </div>
            <div class="policy-trend">
              <span class="trend-label">7D Change:</span>
              <span :class="policy.trend > 0 ? 'positive' : 'negative'">
                {{ policy.trend > 0 ? '+' : '-' }}{{ Math.abs(policy.trend * 100).toFixed(1) }}%
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <span class="card-title">Monte Carlo Scenario Distribution</span>
        </div>
        <div class="scenario-grid">
          <div v-for="scenario in scenarios" :key="scenario.name" class="scenario-item">
            <div class="scenario-name">{{ scenario.name }}</div>
            <div class="scenario-prob">{{ formatPercent(scenario.probability) }}</div>
            <div class="scenario-impact" :class="scenario.impact > 0 ? 'positive' : 'negative'">
              {{ scenario.impact > 0 ? '+' : '' }}{{ scenario.impact.toFixed(2) }}%
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- News Feed with LLM Analysis -->
    <div class="card" style="margin-top: 16px;">
      <div class="card-header">
        <span class="card-title">Recent News Analysis</span>
        <div class="filter-tags">
          <button 
            v-for="tag in filterTags" 
            :key="tag"
            class="filter-tag"
            :class="{ active: activeFilters.includes(tag) }"
            @click="toggleFilter(tag)"
          >
            {{ tag }}
          </button>
        </div>
      </div>
      <div class="news-feed">
        <div v-for="article in filteredArticles" :key="article.id" class="news-item">
          <div class="news-time">{{ formatDate(article.publishedAt) }}</div>
          <div class="news-headline">{{ article.headline }}</div>
          <div class="news-summary">{{ article.llmSummary }}</div>
          <div class="news-analysis">
            <div class="analysis-item">
              <span class="analysis-label">Sentiment:</span>
              <span class="badge" :class="getSentimentBadge(article.sentiment)">
                {{ formatScore(article.sentiment) }}
              </span>
            </div>
            <div class="analysis-item">
              <span class="analysis-label">Impact:</span>
              <span class="badge badge-blue">{{ article.impactLevel }}</span>
            </div>
            <div class="analysis-item">
              <span class="analysis-label">Probability Effect:</span>
              <span :class="article.probEffect > 0 ? 'positive' : 'negative'">
                {{ article.probEffect > 0 ? '+' : '' }}{{ (article.probEffect * 100).toFixed(1) }}%
              </span>
            </div>
          </div>
          <div class="news-tags">
            <span v-for="bucket in article.buckets" :key="bucket" class="badge badge-blue">
              {{ bucket }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import LWChart from '../components/charts/LWChart.vue'

const overallSentiment = ref(null)
const articleCount = ref(null)
const policyImpact = ref(null)
const majorEvents = ref(null)

const sentimentSeries = ref([])

const policySentiment = ref([
  { category: 'China Trade', sentiment: null, trend: null },
  { category: 'Tariff Policy', sentiment: null, trend: null },
  { category: 'Fed/Macro', sentiment: null, trend: null },
  { category: 'Biofuel Mandates', sentiment: null, trend: null },
  { category: 'Energy Policy', sentiment: null, trend: null },
])

const scenarios = ref([])

const filterTags = ['All', 'China', 'Tariff', 'Biofuel', 'Fed', 'Energy']
const activeFilters = ref(['All'])

const articles = ref([])

const filteredArticles = computed(() => {
  if (activeFilters.value.includes('All')) return articles.value
  return articles.value.filter(a => 
    a.buckets.some(b => activeFilters.value.includes(b))
  )
})

const overallSentimentClass = computed(() => {
  if (overallSentiment.value > 0.2) return 'positive'
  if (overallSentiment.value < -0.2) return 'negative'
  return 'neutral'
})

const policyImpactClass = computed(() => {
  if (policyImpact.value > 0.6) return 'positive'
  if (policyImpact.value < 0.4) return 'negative'
  return 'neutral'
})

const sentimentBarWidth = computed(() => {
  return ((overallSentiment.value + 1) / 2 * 100) + '%'
})

function formatScore(val) {
  return val >= 0 ? '+' + val.toFixed(2) : val.toFixed(2)
}

function formatPercent(val) {
  return (val * 100).toFixed(1) + '%'
}

function formatDate(date) {
  const d = new Date(date)
  const now = new Date()
  const diffHours = Math.floor((now - d) / 3600000)
  
  if (diffHours < 1) return 'Just now'
  if (diffHours < 24) return `${diffHours}h ago`
  return d.toLocaleDateString()
}

function getSentimentBadge(sentiment) {
  if (sentiment > 0.3) return 'badge-green'
  if (sentiment < -0.3) return 'badge-red'
  return 'badge-orange'
}

function toggleFilter(tag) {
  if (tag === 'All') {
    activeFilters.value = ['All']
  } else {
    activeFilters.value = activeFilters.value.filter(t => t !== 'All')
    const idx = activeFilters.value.indexOf(tag)
    if (idx >= 0) {
      activeFilters.value.splice(idx, 1)
      if (activeFilters.value.length === 0) activeFilters.value = ['All']
    } else {
      activeFilters.value.push(tag)
    }
  }
}

async function fetchSentimentData() {
  try {
    const [seriesRes, summaryRes, articlesRes] = await Promise.all([
      fetch('/api/sentiment/series?limit=90'),
      fetch('/api/sentiment/summary'),
      fetch('/api/sentiment/articles'),
    ])
    
    if (seriesRes.ok) {
      const data = await seriesRes.json()
      if (data.series?.length) sentimentSeries.value = data.series
    }
    
    if (summaryRes.ok) {
      const data = await summaryRes.json()
      if (data.overall != null) overallSentiment.value = data.overall
      if (data.articleCount != null) articleCount.value = data.articleCount
      if (data.policyImpact != null) policyImpact.value = data.policyImpact
      if (data.majorEvents != null) majorEvents.value = data.majorEvents
      if (data.policySentiment) policySentiment.value = data.policySentiment
      if (data.scenarios) scenarios.value = data.scenarios
    }
    
    if (articlesRes.ok) {
      const data = await articlesRes.json()
      if (data.articles) articles.value = data.articles
    }
  } catch (err) {
    console.error('Failed to fetch sentiment data:', err)
  }
}

onMounted(() => {
  fetchSentimentData()
})
</script>

<style scoped>
.policy-breakdown {
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

.policy-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.policy-icon { font-size: 18px; }
.policy-name { flex: 1; font-weight: 500; }
.policy-score { font-weight: 700; }
.policy-score.positive { color: var(--tv-green); }
.policy-score.negative { color: var(--tv-red); }

.policy-trend {
  margin-top: 8px;
  font-size: 12px;
  color: var(--tv-text-muted);
}

.trend-label { margin-right: 4px; }
.positive { color: var(--tv-green); }
.negative { color: var(--tv-red); }

.scenario-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.scenario-item {
  display: flex;
  align-items: center;
  padding: 12px;
  background: var(--tv-bg-primary);
  border-radius: 6px;
  border: 1px solid var(--tv-border);
}

.scenario-name { flex: 1; font-weight: 500; }
.scenario-prob { font-weight: 700; color: var(--tv-text-primary); margin-right: 16px; }
.scenario-impact { font-weight: 600; }

.filter-tags {
  display: flex;
  gap: 8px;
}

.filter-tag {
  padding: 4px 12px;
  border-radius: 4px;
  background: var(--tv-bg-tertiary);
  border: 1px solid var(--tv-border);
  color: var(--tv-text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.filter-tag:hover {
  background: var(--tv-bg-secondary);
  color: var(--tv-text-primary);
}

.filter-tag.active {
  background: var(--tv-green);
  border-color: var(--tv-green);
  color: white;
}

.news-feed {
  max-height: 600px;
  overflow-y: auto;
}

.news-analysis {
  display: flex;
  gap: 24px;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--tv-border);
}

.analysis-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.analysis-label {
  color: var(--tv-text-muted);
}
</style>
