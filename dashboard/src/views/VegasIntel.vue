<template>
  <div class="vegas-page">
    <header class="page-header">
      <h1 class="page-title">Vegas Intel</h1>
      <p class="page-description">Sales intelligence | Client opportunities | Market positioning</p>
    </header>

    <!-- Coming Soon Notice -->
    <div class="coming-soon-card">
      <h2>Vegas Intel Module</h2>
      <p class="description">
        This page will contain proprietary sales intelligence tools for the US Oil Solutions team.
        Content specifications are pending.
      </p>
      
      <div class="features-preview">
        <h3>Planned Features</h3>
        <ul class="feature-list">
          <li>
            <span class="feature-text">Client opportunity scoring</span>
          </li>
          <li>
            <span class="feature-text">Procurement timing recommendations</span>
          </li>
          <li>
            <span class="feature-text">Competitive positioning analysis</span>
          </li>
          <li>
            <span class="feature-text">Client talking points generator</span>
          </li>
          <li>
            <span class="feature-text">Deal risk assessment</span>
          </li>
        </ul>
      </div>
      
      <div class="status-info">
        <div class="status-badge">
          <span class="status-dot"></span>
          Awaiting Specifications
        </div>
        <p class="status-text">
          Kevin's specs document will define the exact features and data requirements for this module.
        </p>
      </div>
    </div>

    <!-- Quick Stats Preview -->
    <div class="grid grid-3" style="margin-top: 24px;">
      <div class="card kpi placeholder">
        <div class="kpi-value">--</div>
        <div class="kpi-label">Active Client Opportunities</div>
      </div>
      <div class="card kpi placeholder">
        <div class="kpi-value">--</div>
        <div class="kpi-label">Avg Opportunity Score</div>
      </div>
      <div class="card kpi placeholder">
        <div class="kpi-value">--</div>
        <div class="kpi-label">This Week's Targets</div>
      </div>
    </div>

    <!-- Data Integration Notes -->
    <div class="card" style="margin-top: 16px;">
      <div class="card-header">
        <span class="card-title">Data Integration Requirements</span>
      </div>
      <div class="integration-notes">
        <p>This module will integrate with the following data sources once specifications are finalized:</p>
        <div class="data-sources">
          <div class="source-item">
            <span class="source-name">Core Forecast Model</span>
            <span class="badge badge-green">Ready</span>
          </div>
          <div class="source-item">
            <span class="source-name">Specialist Signals</span>
            <span class="badge badge-green">Ready</span>
          </div>
          <div class="source-item">
            <span class="source-name">Monte Carlo Scenarios</span>
            <span class="badge badge-green">Ready</span>
          </div>
          <div class="source-item">
            <span class="source-name">Client Database</span>
            <span class="badge badge-orange">Pending</span>
          </div>
          <div class="source-item">
            <span class="source-name">Deal Pipeline</span>
            <span class="badge badge-orange">Pending</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// Vegas Intel module - awaiting specifications
// This page will be populated once Kevin's specs are available
</script>

<style scoped>
.coming-soon-card {
  background: linear-gradient(135deg, var(--tv-bg-secondary), var(--tv-bg-tertiary));
  border: 2px solid var(--tv-border);
  border-radius: 12px;
  padding: 48px;
  text-align: center;
  margin-top: 16px;
}

.coming-soon-card .icon {
  font-size: 64px;
  margin-bottom: 16px;
}

.coming-soon-card h2 {
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 12px;
  color: var(--tv-text-primary);
}

.coming-soon-card .description {
  font-size: 16px;
  color: var(--tv-text-secondary);
  max-width: 500px;
  margin: 0 auto 32px;
  line-height: 1.6;
}

.features-preview {
  background: var(--tv-bg-primary);
  border-radius: 8px;
  padding: 24px;
  margin-bottom: 24px;
  text-align: left;
  max-width: 400px;
  margin-left: auto;
  margin-right: auto;
}

.features-preview h3 {
  font-size: 14px;
  font-weight: 600;
  color: var(--tv-text-muted);
  text-transform: uppercase;
  margin-bottom: 16px;
}

.feature-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.feature-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid var(--tv-border);
}

.feature-list li:last-child {
  border-bottom: none;
}

.feature-icon {
  font-size: 18px;
}

.feature-text {
  color: var(--tv-text-secondary);
  font-size: 14px;
}

.status-info {
  padding-top: 24px;
  border-top: 1px solid var(--tv-border);
}

.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: var(--tv-bg-primary);
  border-radius: 20px;
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 12px;
}

.status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--tv-orange);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { opacity: 1; }
  50% { opacity: 0.5; }
  100% { opacity: 1; }
}

.status-text {
  font-size: 13px;
  color: var(--tv-text-muted);
}

.placeholder {
  opacity: 0.5;
}

.integration-notes p {
  color: var(--tv-text-secondary);
  margin-bottom: 16px;
  font-size: 14px;
}

.data-sources {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.source-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px;
  background: var(--tv-bg-primary);
  border-radius: 6px;
  border: 1px solid var(--tv-border);
}

.source-name {
  font-weight: 500;
  font-size: 13px;
}

.grid-3 {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}

@media (max-width: 768px) {
  .grid-3 {
    grid-template-columns: 1fr;
  }
}
</style>
