<template>
    <div class="page-home">

    <!-- Hero Section -->
    <section class="hero">
        <div class="hero-container">
            <div class="hero-content">
                <h1 class="hero-title">Soybean Oil Intelligence Platform</h1>
                <p class="hero-subtitle">AI-enhanced commodity forecasting with institutional-grade accuracy. Precision-trained models from 847+ global data sources.</p>
                
                <div class="hero-stats">
                    <div class="stat-item">
                        <div class="stat-number">&lt;3%</div>
                        <div class="stat-label">MAPE Target</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">12</div>
                        <div class="stat-label">Specialists</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-number">24/7</div>
                        <div class="stat-label">Trained Sources</div>
                    </div>
                </div>
            </div>
            
            <div class="hero-visual">
                <div class="data-cube">
                    <div class="cube-face front">
                        <div class="data-points">
                            <div class="data-point"></div>
                            <div class="data-point"></div>
                            <div class="data-point"></div>
                            <div class="data-point"></div>
                        </div>
                    </div>
                    <div class="cube-face back"></div>
                    <div class="cube-face right"></div>
                    <div class="cube-face left"></div>
                    <div class="cube-face top"></div>
                    <div class="cube-face bottom"></div>
                </div>
            </div>
        </div>
    </section>

    <!-- Primary Price Chart -->
    <section class="primary-chart">
        <div class="chart-container">
            <div class="chart-header">
                <h2 class="chart-title">ZL Futures — Regime Analysis</h2>
                <div class="time-range-toggle">
                    <button class="range-btn">1w</button>
                    <button class="range-btn active">1m</button>
                    <button class="range-btn">3m</button>
                    <button class="range-btn">6m</button>
                </div>
            </div>
            
            <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                <div class="chart-area">
                    <div class="regime-ribbons">
                        <div class="regime-ribbon crisis"></div>
                        <div class="regime-ribbon normal"></div>
                    </div>
                    
                    <div class="price-line"></div>
                    
                    <div class="event-markers">
                        <div class="event-marker high-score"></div>
                        <div class="event-marker medium-score"></div>
                    </div>
                    
                    <div class="forecast-bands"></div>
                    
                    <div class="chart-tooltip">
                        <div><strong>$48.78</strong> — Jan 3, 2026</div>
                        <div>Market: STABLE</div>
                        <div>Event: WASDE Report (Score: 78)</div>
                    </div>

                    <div class="chart-cta">
                        <span>View Full Dashboard</span>
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M5 12h14M12 5l7 7-7 7"/>
                        </svg>
                    </div>
                </div>
            </router-link>
        </div>
    </section>

    <!-- Intelligence Grid -->
    <section class="intelligence-grid">
        <div class="grid-container">
            <h2 class="section-title">The Specialist Ensemble</h2>
            <p class="section-subtitle">Twelve domain models, trained in isolation, united in conviction.</p>
            
            <div class="intelligence-cards">
                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
                        </div>
                        <h3 class="card-title">Crush Economics</h3>
                        <p class="card-description">ZL/ZS/ZM spread analysis, NOPA crush margins, and processing economics driving 28-35% of price variance.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">+0.65</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">28%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="10"/><path d="M2 12h20M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/></svg>
                        </div>
                        <h3 class="card-title">China Demand</h3>
                        <p class="card-description">GACC import flows, MOFCOM policy tracking, and CNY-denominated demand signals affecting 16-22% of variance.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">-0.32</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">18%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/></svg>
                        </div>
                        <h3 class="card-title">Energy Complex</h3>
                        <p class="card-description">Crude oil correlations, heating oil spreads, BOHO ratio tracking, and renewable diesel margins.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">+0.45</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">12%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><path d="M12 1v22M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>
                        </div>
                        <h3 class="card-title">FX Dynamics</h3>
                        <p class="card-description">DXY index movements, USD/BRL cross-rates, and currency impacts on export competitiveness.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">-0.18</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">9%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><path d="M3 3v18h18"/><path d="M18 17V9"/><path d="M13 17V5"/><path d="M8 17v-3"/></svg>
                        </div>
                        <h3 class="card-title">Fed Policy</h3>
                        <p class="card-description">Interest rate expectations, FOMC sentiment, yield curve dynamics, and liquidity conditions.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">+0.22</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">8%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z"/><line x1="7" y1="7" x2="7.01" y2="7"/></svg>
                        </div>
                        <h3 class="card-title">Tariff Regime</h3>
                        <p class="card-description">Section 301 developments, retaliatory duties, trade policy shifts, and biofuel import tariffs.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">+0.71</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">11%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><path d="M12 3v18M5.5 8.5l13-1M5.5 15.5l13 1"/><circle cx="12" cy="12" r="1"/></svg>
                        </div>
                        <h3 class="card-title">Biofuel Mandate</h3>
                        <p class="card-description">RFS volumes, RIN pricing, SAF demand forecasts, and renewable diesel capacity buildout.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">+0.54</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">14%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/></svg>
                        </div>
                        <h3 class="card-title">Palm Substitution</h3>
                        <p class="card-description">MPOB inventory levels, CPO/SBO spreads, Indonesian export levies, and substitution elasticity.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">-0.29</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">10%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>
                        </div>
                        <h3 class="card-title">Volatility Regime</h3>
                        <p class="card-description">OVX energy vol, CVOL agricultural implied vol, regime detection, and risk-on/risk-off signals.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">+0.38</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">7%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><path d="M16 3h5v5M4 20L21 3M21 16v5h-5M15 15l6 6M4 4l5 5"/></svg>
                        </div>
                        <h3 class="card-title">Substitutes</h3>
                        <p class="card-description">Canola, sunflower, and competing vegetable oil spreads driving cross-commodity arbitrage flows.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">+0.12</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">6%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><path d="M12 2l3.09 6.26L22 9.27l-5 4.87 1.18 6.88L12 17.77l-6.18 3.25L7 14.14 2 9.27l6.91-1.01L12 2z"/></svg>
                        </div>
                        <h3 class="card-title">Trump Effect</h3>
                        <p class="card-description">Executive policy volatility, trade rhetoric intensity, and political event risk scoring across all domains.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">+0.58</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">9%</div>
                                <div class="metric-label">Weight</div>
                            </div>
                        </div>
                    </div>
                </router-link>

                <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                    <div class="intel-card core-card">
                        <div class="card-icon">
                            <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v6M12 17v6M4.22 4.22l4.24 4.24M15.54 15.54l4.24 4.24M1 12h6M17 12h6M4.22 19.78l4.24-4.24M15.54 8.46l4.24-4.24"/></svg>
                        </div>
                        <h3 class="card-title">Core Baseline</h3>
                        <p class="card-description">Chronos-2 foundation model capturing global market context and temporal patterns across all features.</p>
                        <div class="card-metrics">
                            <div class="metric">
                                <div class="metric-value">+0.41</div>
                                <div class="metric-label">Signal</div>
                            </div>
                            <div class="metric">
                                <div class="metric-value">—</div>
                                <div class="metric-label">Anchor</div>
                            </div>
                        </div>
                    </div>
                </router-link>
            </div>
        </div>
    </section>

    <!-- Signal Preview -->
    <section class="signal-preview">
        <div class="preview-container">
            <h2 class="preview-title">Model Signal Dashboard</h2>
            <p class="preview-subtitle">Current market intelligence and multi-horizon forecasting</p>
            
            <div class="signal-display">
                <!-- Chris's Big 4 Gauges -->
                <div class="big-four-gauges">
                    <div class="gauge-container">
                        <div class="gauge-title">VIX Stress</div>
                        <div class="gauge-visual">
                            <div class="gauge-arc"></div>
                            <div class="gauge-fill vix"></div>
                        </div>
                        <div class="gauge-value">1.85</div>
                        <div class="gauge-subtext">Current: 31.2<br>Normal: 20.0</div>
                        <div class="weight-contribution">Weight: 68%</div>
                    </div>
                    
                    <div class="gauge-container">
                        <div class="gauge-title">Harvest Pace</div>
                        <div class="gauge-visual">
                            <div class="gauge-arc"></div>
                            <div class="gauge-fill harvest"></div>
                        </div>
                        <div class="gauge-value">0.76</div>
                        <div class="gauge-subtext">SA Combined<br>76% of Normal</div>
                        <div class="weight-contribution">Weight: 45%</div>
                    </div>
                    
                    <div class="gauge-container">
                        <div class="gauge-title">China Tension</div>
                        <div class="gauge-visual">
                            <div class="gauge-arc"></div>
                            <div class="gauge-fill china"></div>
                        </div>
                        <div class="gauge-value">0.74</div>
                        <div class="gauge-subtext">Trade Relations<br>High Tension</div>
                        <div class="weight-contribution">Weight: 15%</div>
                    </div>
                    
                    <div class="gauge-container">
                        <div class="gauge-title">Tariff Threat</div>
                        <div class="gauge-visual">
                            <div class="gauge-arc"></div>
                            <div class="gauge-fill tariff"></div>
                        </div>
                        <div class="gauge-value">0.89</div>
                        <div class="gauge-subtext">7-Day Mentions<br>Elevated Risk</div>
                        <div class="weight-contribution">Weight: 70%</div>
                    </div>
                </div>
                
                <div class="current-signal">
                    <div class="signal-item">
                        <div class="signal-value">$48.78</div>
                        <div class="signal-label">Current ZL Price</div>
                    </div>
                    <div class="signal-item">
                        <div class="signal-value">STABLE</div>
                        <div class="signal-label">Market</div>
                    </div>
                    <div class="signal-item">
                        <div class="signal-value">72%</div>
                        <div class="signal-label">Confidence</div>
                    </div>
                    <div class="signal-item">
                        <div class="signal-value">WAIT</div>
                        <div class="signal-label">Posture</div>
                    </div>
                </div>
                
                <div class="forecast-horizons">
                    <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                        <div class="horizon-card">
                            <div class="horizon-period">1w</div>
                            <div class="horizon-price">$49.12</div>
                            <div class="horizon-move">+$0.34 (±$0.85)</div>
                            <div class="bullish-percent">58% Bullish</div>
                            <div class="sparkline"></div>
                        </div>
                    </router-link>
                    <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                        <div class="horizon-card">
                            <div class="horizon-period">1m</div>
                            <div class="horizon-price">$50.45</div>
                            <div class="horizon-move">+$1.67</div>
                            <div class="bullish-percent">62% Bullish</div>
                            <div class="sparkline"></div>
                        </div>
                    </router-link>
                    <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                        <div class="horizon-card">
                            <div class="horizon-period">3m</div>
                            <div class="horizon-price">$52.18</div>
                            <div class="horizon-move">+$3.40</div>
                            <div class="bullish-percent">65% Bullish</div>
                            <div class="sparkline"></div>
                        </div>
                    </router-link>
                    <router-link to="/dashboard" style="text-decoration: none; color: inherit;">
                        <div class="horizon-card">
                            <div class="horizon-period">6m</div>
                            <div class="horizon-price">$54.92</div>
                            <div class="horizon-move">+$6.14</div>
                            <div class="bullish-percent">61% Bullish</div>
                            <div class="sparkline"></div>
                        </div>
                    </router-link>
                </div>

                <router-link to="/dashboard" class="view-dashboard-link">
                    View Full Dashboard
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M5 12h14M12 5l7 7-7 7"/>
                    </svg>
                </router-link>
            </div>
        </div>
    </section>

    <!-- CTA Section -->
    <section class="cta-section">
        <div class="cta-container">
            <h2 class="cta-title">Institutional-Grade Intelligence</h2>
            <p class="cta-description">Access the same commodity intelligence platform trusted by procurement teams and trading desks.</p>
            <router-link to="/dashboard" class="cta-button">Access Dashboard</router-link>
        </div>
    </section>

    <!-- Footer -->
    <footer class="footer">
        <div class="footer-container">
            <p class="footer-text">© 2026 ZINC Fusion V15 Intelligence. All rights reserved.</p>
        </div>
    </footer>

    </div>
</template>

<script setup>
</script>

<style scoped>
</style>
