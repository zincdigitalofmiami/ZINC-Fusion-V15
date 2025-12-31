<script setup>
/**
 * PostureStrip.vue
 * 
 * Market posture indicator strip.
 * Red / Yellow / Green with narrative context.
 */

const props = defineProps({
  posture: {
    type: Object,
    required: true,
    // { level: 'red'|'yellow'|'green', narrative: string, downsideRisk?: number, timingRisk?: number }
  },
})

const postureLabels = {
  green: 'Favorable Conditions',
  yellow: 'Neutral / Watchful',
  red: 'Elevated Risk',
}

const postureDescriptions = {
  green: 'Downside risk dominates timing risk. Waiting carries higher expected cost.',
  yellow: 'Risks are balanced. Timing matters more than direction.',
  red: 'Timing risk dominates. Waiting is statistically safer than committing.',
}
</script>

<template>
  <div class="posture-strip" :class="posture.level">
    <div class="posture-main">
      <span class="posture-dot"></span>
      <div class="posture-content">
        <div class="posture-header">
          <span class="posture-label">Market Posture:</span>
          <span class="posture-value">{{ postureLabels[posture.level] }}</span>
        </div>
        <p class="posture-description">{{ postureDescriptions[posture.level] }}</p>
      </div>
    </div>
    
    <div class="posture-narrative" v-if="posture.narrative">
      <p>{{ posture.narrative }}</p>
    </div>
    
    <div class="posture-risks" v-if="posture.downsideRisk !== undefined">
      <div class="risk-item">
        <span class="risk-label">Downside Risk</span>
        <div class="risk-bar">
          <div class="risk-fill downside" :style="{ width: (posture.downsideRisk * 100) + '%' }"></div>
        </div>
        <span class="risk-value">{{ Math.round(posture.downsideRisk * 100) }}%</span>
      </div>
      <div class="risk-item">
        <span class="risk-label">Timing Risk</span>
        <div class="risk-bar">
          <div class="risk-fill timing" :style="{ width: (posture.timingRisk * 100) + '%' }"></div>
        </div>
        <span class="risk-value">{{ Math.round(posture.timingRisk * 100) }}%</span>
      </div>
    </div>
    
    <p class="posture-disclaimer">This is not a recommendation. It is a probabilistic assessment of exposure.</p>
  </div>
</template>

<style scoped>
.posture-strip {
  padding: var(--spacing-lg, 16px) var(--spacing-xl, 20px);
  border-top: 1px solid var(--border-soft, rgba(255,255,255,0.08));
  border-bottom: 1px solid var(--border-soft, rgba(255,255,255,0.08));
  background: var(--bg-panel, #111827);
}

.posture-strip.green {
  border-left: 3px solid var(--signal-green, #4ADE80);
}

.posture-strip.yellow {
  border-left: 3px solid var(--signal-yellow, #FACC15);
}

.posture-strip.red {
  border-left: 3px solid var(--signal-red, #F87171);
}

.posture-main {
  display: flex;
  align-items: flex-start;
  gap: var(--spacing-md, 12px);
}

.posture-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  margin-top: 4px;
  flex-shrink: 0;
}

.posture-strip.green .posture-dot { background: var(--signal-green, #4ADE80); }
.posture-strip.yellow .posture-dot { background: var(--signal-yellow, #FACC15); }
.posture-strip.red .posture-dot { background: var(--signal-red, #F87171); }

.posture-content {
  flex: 1;
}

.posture-header {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-sm, 8px);
  margin-bottom: var(--spacing-xs, 4px);
}

.posture-label {
  font-size: var(--font-size-sm, 12px);
  color: var(--text-muted, #6B7280);
}

.posture-value {
  font-size: var(--font-size-md, 14px);
  font-weight: 600;
  color: var(--text-primary, #E5E7EB);
}

.posture-description {
  font-size: var(--font-size-sm, 12px);
  color: var(--text-secondary, #AEB6C1);
  margin: 0;
  line-height: 1.5;
}

.posture-narrative {
  margin-top: var(--spacing-md, 12px);
  padding-top: var(--spacing-md, 12px);
  border-top: 1px solid var(--border-subtle, rgba(255,255,255,0.04));
}

.posture-narrative p {
  margin: 0;
  font-size: var(--font-size-base, 13px);
  color: var(--text-secondary, #AEB6C1);
  font-style: italic;
  line-height: 1.6;
}

.posture-risks {
  display: flex;
  gap: var(--spacing-2xl, 24px);
  margin-top: var(--spacing-lg, 16px);
  padding-top: var(--spacing-md, 12px);
  border-top: 1px solid var(--border-subtle, rgba(255,255,255,0.04));
}

.risk-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  flex: 1;
}

.risk-label {
  font-size: var(--font-size-xs, 11px);
  color: var(--text-muted, #6B7280);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  min-width: 90px;
}

.risk-bar {
  flex: 1;
  height: 4px;
  background: var(--bg-card, #0F172A);
  border-radius: 2px;
  overflow: hidden;
}

.risk-fill {
  height: 100%;
  border-radius: 2px;
  transition: width var(--transition-slow, 240ms ease-in-out);
}

.risk-fill.downside { background: var(--signal-red, #F87171); }
.risk-fill.timing { background: var(--signal-yellow, #FACC15); }

.risk-value {
  font-size: var(--font-size-sm, 12px);
  font-weight: 600;
  color: var(--text-secondary, #AEB6C1);
  min-width: 36px;
  text-align: right;
}

.posture-disclaimer {
  margin: var(--spacing-md, 12px) 0 0 0;
  padding-top: var(--spacing-md, 12px);
  border-top: 1px solid var(--border-subtle, rgba(255,255,255,0.04));
  font-size: var(--font-size-xs, 11px);
  color: var(--text-faint, #4B5563);
  font-style: italic;
}
</style>
