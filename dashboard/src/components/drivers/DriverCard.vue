<script setup>
/**
 * DriverCard.vue
 * 
 * Individual driver signal card.
 * Communicates direction + confidence + narrative only.
 * No charts in cards.
 */

const props = defineProps({
  driver: {
    type: Object,
    required: true,
    // { key, label, icon, signal: 'up'|'down'|'flat', confidence, note }
  },
})

const signalArrows = {
  up: 'UP',
  down: 'DN',
  flat: '--',
}

const signalLabels = {
  up: 'Upward',
  down: 'Downward',
  flat: 'Neutral',
}
</script>

<template>
  <div class="driver-card" :class="driver.signal">
    <header class="card-header">
      <h4 class="card-label">{{ driver.label }}</h4>
    </header>
    
    <div class="card-signal">
      <span class="signal-arrow">{{ signalArrows[driver.signal] }}</span>
      <span class="signal-label">{{ signalLabels[driver.signal] }}</span>
    </div>
    
    <p class="card-note">{{ driver.note }}</p>
    
    <div class="card-confidence">
      <span class="confidence-label">Confidence:</span>
      <span class="confidence-value">{{ Math.round(driver.confidence * 100) }}%</span>
    </div>
  </div>
</template>

<style scoped>
.driver-card {
  background: var(--bg-card, #0F172A);
  border: 1px solid var(--border-soft, rgba(255,255,255,0.08));
  border-radius: var(--radius-md, 6px);
  padding: var(--spacing-lg, 16px);
  transition: border-color var(--transition-fast, 120ms ease-out);
}

.driver-card:hover {
  border-color: rgba(255, 255, 255, 0.12);
}

.driver-card.up {
  border-top: 2px solid var(--signal-green, #4ADE80);
}

.driver-card.down {
  border-top: 2px solid var(--signal-red, #F87171);
}

.driver-card.flat {
  border-top: 2px solid var(--signal-yellow, #FACC15);
}

.card-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm, 8px);
  margin-bottom: var(--spacing-md, 12px);
}

.card-icon {
  font-size: 16px;
}

.card-label {
  font-size: var(--font-size-base, 13px);
  font-weight: 600;
  color: var(--text-secondary, #AEB6C1);
  margin: 0;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.card-signal {
  display: flex;
  align-items: baseline;
  gap: var(--spacing-sm, 8px);
  margin-bottom: var(--spacing-md, 12px);
}

.signal-arrow {
  font-size: 20px;
  font-weight: 700;
  line-height: 1;
}

.driver-card.up .signal-arrow { color: var(--signal-green, #4ADE80); }
.driver-card.down .signal-arrow { color: var(--signal-red, #F87171); }
.driver-card.flat .signal-arrow { color: var(--signal-yellow, #FACC15); }

.signal-label {
  font-size: var(--font-size-xs, 11px);
  color: var(--text-muted, #6B7280);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.card-note {
  font-size: var(--font-size-sm, 12px);
  color: var(--text-secondary, #AEB6C1);
  line-height: 1.5;
  margin: 0 0 var(--spacing-md, 12px) 0;
}

.card-confidence {
  display: flex;
  align-items: center;
  gap: var(--spacing-xs, 4px);
  padding-top: var(--spacing-sm, 8px);
  border-top: 1px solid var(--border-subtle, rgba(255,255,255,0.04));
}

.confidence-label {
  font-size: var(--font-size-xs, 11px);
  color: var(--text-muted, #6B7280);
}

.confidence-value {
  font-size: var(--font-size-sm, 12px);
  font-weight: 600;
  color: var(--text-secondary, #AEB6C1);
}
</style>
