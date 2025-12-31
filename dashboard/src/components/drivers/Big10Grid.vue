<script setup>
/**
 * Big10Grid.vue
 * 
 * Strict 4-column grid for Big-10 driver cards.
 * Fixed layout, no masonry, no random floating.
 */

import DriverCard from './DriverCard.vue'

const props = defineProps({
  drivers: {
    type: Array,
    required: true,
    // Array of { key, label, icon, signal, confidence, note }
  },
})
</script>

<template>
  <section class="big10-section">
    <header class="section-header">
      <h3 class="section-title">Big-10 Signal Summary</h3>
      <p class="section-subtitle">Directional, Not Actionable. No single driver is decisive. Confluence matters.</p>
    </header>
    
    <div class="big10-grid">
      <DriverCard 
        v-for="driver in drivers" 
        :key="driver.key" 
        :driver="driver" 
      />
    </div>
  </section>
</template>

<style scoped>
.big10-section {
  padding: var(--spacing-xl, 20px);
}

.section-header {
  margin-bottom: var(--spacing-lg, 16px);
}

.section-title {
  font-size: var(--font-size-lg, 16px);
  font-weight: 600;
  color: var(--text-primary, #E5E7EB);
  margin: 0 0 var(--spacing-xs, 4px) 0;
}

.section-subtitle {
  font-size: var(--font-size-sm, 12px);
  color: var(--text-muted, #6B7280);
  margin: 0;
}

.big10-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--spacing-lg, 16px);
}

/* Responsive: 3 columns on medium screens */
@media (max-width: 1100px) {
  .big10-grid {
    grid-template-columns: repeat(3, 1fr);
  }
}

/* Responsive: 2 columns on smaller screens */
@media (max-width: 768px) {
  .big10-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}

/* Responsive: 1 column on mobile */
@media (max-width: 480px) {
  .big10-grid {
    grid-template-columns: 1fr;
  }
}
</style>
