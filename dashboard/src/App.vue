<template>
  <div class="app">
    <!-- TOP NAV (TradingView-style) -->
    <nav class="top-nav">
      <div class="nav-left">
        <div class="nav-brand">
          <span class="brand-icon">Z</span>
          <div class="brand-text">
            <span class="brand-name">ZINC FUSION</span>
            <span class="brand-version">V15 INTEL</span>
          </div>
        </div>
      </div>

      <div class="nav-links">
        <router-link to="/" :class="{ active: $route.path === '/' }">Dashboard</router-link>
        <router-link to="/strategy" :class="{ active: $route.path === '/strategy' }">Strategy</router-link>
        <router-link to="/sentiment" :class="{ active: $route.path === '/sentiment' }">Sentiment</router-link>
        <router-link to="/legislation" :class="{ active: $route.path === '/legislation' }">Legislation / Trade</router-link>
        <router-link to="/vegas-intel" :class="{ active: $route.path === '/vegas-intel' }">Vegas Intel</router-link>
      </div>

      <div class="nav-right">
        <div class="system-status" :class="{ active: systemActive }">
          <span class="status-dot"></span>
          <span class="status-text">System Active</span>
        </div>
        <div class="user-avatar">JD</div>
      </div>
    </nav>

    <!-- MAIN CONTENT -->
    <main class="main">
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'

const systemActive = ref(true)

// Check system health periodically
async function checkSystemHealth() {
  try {
    const res = await fetch('/api/zl/price?days=1')
    systemActive.value = res.ok
  } catch {
    systemActive.value = false
  }
}

onMounted(() => {
  checkSystemHealth()
  setInterval(checkSystemHealth, 60000) // Check every minute
})
</script>

<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  background: #131722;
  color: #D1D4DC;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

.app {
  min-height: 100vh;
}

/* TOP NAV - TradingView Style */
.top-nav {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  height: 48px;
  background: #1E222D;
  border-bottom: 1px solid #2A2E39;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1rem;
  z-index: 100;
}

.nav-left {
  display: flex;
  align-items: center;
}

.nav-brand {
  display: flex;
  align-items: center;
  gap: 0.625rem;
}

.brand-icon {
  width: 26px;
  height: 26px;
  background: #2962FF;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 0.8125rem;
  color: #FFFFFF;
  font-family: 'Inter', sans-serif;
}

.brand-text {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.brand-name {
  font-weight: 600;
  font-size: 0.75rem;
  letter-spacing: 0.02em;
  color: #D1D4DC;
}

.brand-version {
  font-size: 0.5625rem;
  color: #787B86;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.nav-links {
  display: flex;
  gap: 0;
}

.nav-links a {
  color: #787B86;
  text-decoration: none;
  font-size: 0.75rem;
  font-weight: 500;
  padding: 0.5rem 0.875rem;
  border-radius: 0;
  transition: all 0.15s;
  font-family: 'Inter', sans-serif;
  letter-spacing: 0.01em;
}

.nav-links a:hover {
  color: #D1D4DC;
}

.nav-links a.active {
  color: #2962FF;
  background: transparent;
  border-bottom: 2px solid #2962FF;
  margin-bottom: -1px;
}

.nav-right {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.system-status {
  display: flex;
  align-items: center;
  gap: 0.375rem;
  font-size: 0.6875rem;
  color: #787B86;
  font-family: 'Inter', sans-serif;
}

.system-status.active .status-dot {
  background: #00E676;
  box-shadow: 0 0 6px rgba(0, 230, 118, 0.5);
}

.system-status.active .status-text {
  color: #B2B5BE;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: #787B86;
  transition: all 0.3s;
}

.status-text {
  transition: color 0.3s;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}

.user-avatar {
  width: 28px;
  height: 28px;
  background: #2A2E39;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.625rem;
  font-weight: 600;
  color: #787B86;
  font-family: 'Inter', sans-serif;
}

/* MAIN */
.main {
  padding-top: 48px;
}

/* Responsive */
@media (max-width: 900px) {
  .nav-links {
    display: none;
  }

  .system-status .status-text {
    display: none;
  }
}
</style>
