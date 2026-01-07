<template>
    <div class="page-dashboard">
        <main class="main-content">

        <div class="dashboard-grid">
            <!-- Left: Chart Area -->
            <div class="chart-area">
                <div class="chart-section">
                    <div class="chart-header">
                        <div>
                            <div class="chart-title">ZL Soybean Oil — Front Month</div>
                            <div class="chart-subtitle">CBOT Futures • Forecast overlay enabled</div>
                        </div>
                        <div class="time-range-selector">
                            <button class="range-btn">1W</button>
                            <button class="range-btn active">1M</button>
                            <button class="range-btn">3M</button>
                            <button class="range-btn">6M</button>
                            <button class="range-btn">1Y</button>
                        </div>
                    </div>
                    
                    <div class="chart-container">
                        <div class="mock-chart">
                            <div class="price-line"></div>
                            <div class="forecast-cone"></div>
                            <div class="p90-line"></div>
                            <div class="p10-line"></div>
                            <div class="price-label current">48.78</div>
                            <div class="price-label p90">52.40</div>
                            <div class="price-label p10">45.20</div>
                        </div>
                    </div>
                </div>

                <!-- Big Four Gauges -->
                <div class="gauges-section">
                    <div class="gauges-title">Key Risk Indicators</div>
                    <div class="gauges-grid">
                        <div class="gauge-card">
                            <div class="gauge-label">VIX Stress</div>
                            <div class="gauge-visual">
                                <div class="gauge-arc"></div>
                                <div class="gauge-needle" style="transform: rotate(-30deg);"></div>
                                <div class="gauge-center"></div>
                            </div>
                            <div class="gauge-value medium">18.2</div>
                            <div class="gauge-context">Normal: &lt;20<br>Elevated: 20-30</div>
                        </div>
                        
                        <div class="gauge-card">
                            <div class="gauge-label">Harvest Pace</div>
                            <div class="gauge-visual">
                                <div class="gauge-arc"></div>
                                <div class="gauge-needle" style="transform: rotate(15deg);"></div>
                                <div class="gauge-center"></div>
                            </div>
                            <div class="gauge-value low">76%</div>
                            <div class="gauge-context">SA Combined<br>76% of Normal</div>
                        </div>
                        
                        <div class="gauge-card">
                            <div class="gauge-label">China Tension</div>
                            <div class="gauge-visual">
                                <div class="gauge-arc"></div>
                                <div class="gauge-needle" style="transform: rotate(35deg);"></div>
                                <div class="gauge-center"></div>
                            </div>
                            <div class="gauge-value high">0.74</div>
                            <div class="gauge-context">Trade Relations<br>High Tension</div>
                        </div>
                        
                        <div class="gauge-card">
                            <div class="gauge-label">Tariff Threat</div>
                            <div class="gauge-visual">
                                <div class="gauge-arc"></div>
                                <div class="gauge-needle" style="transform: rotate(55deg);"></div>
                                <div class="gauge-center"></div>
                            </div>
                            <div class="gauge-value high">0.89</div>
                            <div class="gauge-context">7-Day Mentions<br>Elevated Risk</div>
                        </div>
                    </div>
                </div>

                <!-- Horizon Forecasts - Semicircular Gauges -->
                <div class="horizon-section">
                    <div class="horizon-title">Forecast Horizons</div>
                    <div class="horizon-grid">
                        <!-- 1W Gauge - Strong Buy -->
                        <div class="gauge-card-hz" style="border-color: rgba(41, 98, 255, 0.4);">
                            <div class="gauge-hz-label">1W FORECAST</div>
                            <div class="gauge-hz-container">
                                <svg viewBox="0 0 200 120" class="gauge-hz-svg">
                                    <!-- Gauge arc background -->
                                    <defs>
                                        <linearGradient id="gaugeGrad1" x1="0%" y1="0%" x2="100%" y2="0%">
                                            <stop offset="0%" style="stop-color:#ef5350"/>
                                            <stop offset="35%" style="stop-color:#ffb74d"/>
                                            <stop offset="50%" style="stop-color:#ffd54f"/>
                                            <stop offset="65%" style="stop-color:#81c784"/>
                                            <stop offset="100%" style="stop-color:#2962FF"/>
                                        </linearGradient>
                                    </defs>
                                    <!-- Arc -->
                                    <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="url(#gaugeGrad1)" stroke-width="12" stroke-linecap="round"/>
                                    <!-- Needle - pointing to Strong Buy (right side) -->
                                    <line x1="100" y1="100" x2="160" y2="55" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
                                    <circle cx="100" cy="100" r="8" fill="#1a1a2e"/>
                                    <circle cx="100" cy="100" r="5" fill="#fff"/>
                                    <!-- Signal label -->
                                    <text x="100" y="85" text-anchor="middle" fill="#2962FF" font-size="11" font-weight="600">Strong Buy</text>
                                </svg>
                            </div>
                            <div class="gauge-hz-price">$49.12</div>
                            <div class="gauge-hz-change positive">+0.70%</div>
                            <div class="gauge-hz-metrics">
                                <div class="gauge-hz-metric"><span>MAE</span><span>1.72</span></div>
                                <div class="gauge-hz-metric"><span>R² Score</span><span>0.956</span></div>
                            </div>
                        </div>

                        <!-- 1M Gauge - Buy -->
                        <div class="gauge-card-hz" style="border-color: rgba(41, 98, 255, 0.3);">
                            <div class="gauge-hz-label">1M FORECAST</div>
                            <div class="gauge-hz-container">
                                <svg viewBox="0 0 200 120" class="gauge-hz-svg">
                                    <defs>
                                        <linearGradient id="gaugeGrad2" x1="0%" y1="0%" x2="100%" y2="0%">
                                            <stop offset="0%" style="stop-color:#ef5350"/>
                                            <stop offset="35%" style="stop-color:#ffb74d"/>
                                            <stop offset="50%" style="stop-color:#ffd54f"/>
                                            <stop offset="65%" style="stop-color:#81c784"/>
                                            <stop offset="100%" style="stop-color:#2962FF"/>
                                        </linearGradient>
                                    </defs>
                                    <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="url(#gaugeGrad2)" stroke-width="12" stroke-linecap="round"/>
                                    <!-- Needle - pointing to Buy -->
                                    <line x1="100" y1="100" x2="145" y2="45" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
                                    <circle cx="100" cy="100" r="8" fill="#1a1a2e"/>
                                    <circle cx="100" cy="100" r="5" fill="#fff"/>
                                    <text x="100" y="85" text-anchor="middle" fill="#81c784" font-size="11" font-weight="600">Buy</text>
                                </svg>
                            </div>
                            <div class="gauge-hz-price">$50.45</div>
                            <div class="gauge-hz-change positive">+3.42%</div>
                            <div class="gauge-hz-metrics">
                                <div class="gauge-hz-metric"><span>MAE</span><span>2.81</span></div>
                                <div class="gauge-hz-metric"><span>R² Score</span><span>0.892</span></div>
                            </div>
                        </div>

                        <!-- 3M Gauge - Neutral -->
                        <div class="gauge-card-hz" style="border-color: rgba(255, 213, 79, 0.3);">
                            <div class="gauge-hz-label">3M FORECAST</div>
                            <div class="gauge-hz-container">
                                <svg viewBox="0 0 200 120" class="gauge-hz-svg">
                                    <defs>
                                        <linearGradient id="gaugeGrad3" x1="0%" y1="0%" x2="100%" y2="0%">
                                            <stop offset="0%" style="stop-color:#ef5350"/>
                                            <stop offset="35%" style="stop-color:#ffb74d"/>
                                            <stop offset="50%" style="stop-color:#ffd54f"/>
                                            <stop offset="65%" style="stop-color:#81c784"/>
                                            <stop offset="100%" style="stop-color:#2962FF"/>
                                        </linearGradient>
                                    </defs>
                                    <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="url(#gaugeGrad3)" stroke-width="12" stroke-linecap="round"/>
                                    <!-- Needle - pointing to Neutral (middle) -->
                                    <line x1="100" y1="100" x2="100" y2="25" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
                                    <circle cx="100" cy="100" r="8" fill="#1a1a2e"/>
                                    <circle cx="100" cy="100" r="5" fill="#fff"/>
                                    <text x="100" y="85" text-anchor="middle" fill="#ffd54f" font-size="11" font-weight="600">Neutral</text>
                                </svg>
                            </div>
                            <div class="gauge-hz-price">$52.18</div>
                            <div class="gauge-hz-change negative">-5.33%</div>
                            <div class="gauge-hz-metrics">
                                <div class="gauge-hz-metric"><span>MAE</span><span>3.69</span></div>
                                <div class="gauge-hz-metric"><span>R² Score</span><span>0.796</span></div>
                            </div>
                        </div>

                        <!-- 6M Gauge - Sell -->
                        <div class="gauge-card-hz" style="border-color: rgba(239, 83, 80, 0.3);">
                            <div class="gauge-hz-label">6M FORECAST</div>
                            <div class="gauge-hz-container">
                                <svg viewBox="0 0 200 120" class="gauge-hz-svg">
                                    <defs>
                                        <linearGradient id="gaugeGrad4" x1="0%" y1="0%" x2="100%" y2="0%">
                                            <stop offset="0%" style="stop-color:#ef5350"/>
                                            <stop offset="35%" style="stop-color:#ffb74d"/>
                                            <stop offset="50%" style="stop-color:#ffd54f"/>
                                            <stop offset="65%" style="stop-color:#81c784"/>
                                            <stop offset="100%" style="stop-color:#2962FF"/>
                                        </linearGradient>
                                    </defs>
                                    <path d="M 20 100 A 80 80 0 0 1 180 100" fill="none" stroke="url(#gaugeGrad4)" stroke-width="12" stroke-linecap="round"/>
                                    <!-- Needle - pointing to Sell (left side) -->
                                    <line x1="100" y1="100" x2="45" y2="50" stroke="#fff" stroke-width="3" stroke-linecap="round"/>
                                    <circle cx="100" cy="100" r="8" fill="#1a1a2e"/>
                                    <circle cx="100" cy="100" r="5" fill="#fff"/>
                                    <text x="100" y="85" text-anchor="middle" fill="#ef5350" font-size="11" font-weight="600">Sell</text>
                                </svg>
                            </div>
                            <div class="gauge-hz-price">$42.10</div>
                            <div class="gauge-hz-change negative">-15.87%</div>
                            <div class="gauge-hz-metrics">
                                <div class="gauge-hz-metric"><span>MAE</span><span>4.52</span></div>
                                <div class="gauge-hz-metric"><span>R² Score</span><span>0.724</span></div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <!-- Right: Sidebar -->
            <div class="sidebar">
                <!-- Posture -->
                <div class="posture-card">
                    <div class="posture-label">Procurement Posture</div>
                    <div class="posture-value wait">WAIT</div>
                    <div class="posture-reason">
                        Models show rising prices at 1m horizon. Current stability suggests waiting for pullback opportunity.
                    </div>
                </div>

                <!-- Specialist Signals -->
                <div class="signals-card">
                    <div class="signals-title">Specialist Ensemble (12 Models)</div>
                    
                    <div class="signal-row">
                        <span class="signal-name">Crush Economics</span>
                        <span class="signal-value positive">+0.65</span>
                        <div class="signal-bar"><div class="signal-bar-fill positive" style="width: 65%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">Tariff Regime</span>
                        <span class="signal-value positive">+0.71</span>
                        <div class="signal-bar"><div class="signal-bar-fill positive" style="width: 71%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">Trump Effect</span>
                        <span class="signal-value positive">+0.58</span>
                        <div class="signal-bar"><div class="signal-bar-fill positive" style="width: 58%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">Biofuel Mandate</span>
                        <span class="signal-value positive">+0.54</span>
                        <div class="signal-bar"><div class="signal-bar-fill positive" style="width: 54%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">Energy Complex</span>
                        <span class="signal-value positive">+0.45</span>
                        <div class="signal-bar"><div class="signal-bar-fill positive" style="width: 45%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">Core Baseline</span>
                        <span class="signal-value positive">+0.41</span>
                        <div class="signal-bar"><div class="signal-bar-fill positive" style="width: 41%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">Volatility Regime</span>
                        <span class="signal-value positive">+0.38</span>
                        <div class="signal-bar"><div class="signal-bar-fill positive" style="width: 38%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">Fed Policy</span>
                        <span class="signal-value positive">+0.22</span>
                        <div class="signal-bar"><div class="signal-bar-fill positive" style="width: 22%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">Substitutes</span>
                        <span class="signal-value positive">+0.12</span>
                        <div class="signal-bar"><div class="signal-bar-fill positive" style="width: 12%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">FX Dynamics</span>
                        <span class="signal-value negative">-0.18</span>
                        <div class="signal-bar"><div class="signal-bar-fill negative" style="width: 18%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">Palm Substitution</span>
                        <span class="signal-value negative">-0.29</span>
                        <div class="signal-bar"><div class="signal-bar-fill negative" style="width: 29%;"></div></div>
                    </div>
                    
                    <div class="signal-row">
                        <span class="signal-name">China Demand</span>
                        <span class="signal-value negative">-0.32</span>
                        <div class="signal-bar"><div class="signal-bar-fill negative" style="width: 32%;"></div></div>
                    </div>
                </div>

                <!-- Key Metrics -->
                <div class="metrics-card">
                    <div class="metrics-title">Key Metrics</div>
                    
                    <div class="metric-row">
                        <span class="metric-label">Model Confidence</span>
                        <span class="metric-value">72%</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">30d MAPE</span>
                        <span class="metric-value">2.4%</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">VIX Level</span>
                        <span class="metric-value">18.2</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Regime</span>
                        <span class="metric-value">Stable</span>
                    </div>
                    <div class="metric-row">
                        <span class="metric-label">Last Training</span>
                        <span class="metric-value">Jan 4, 6:00 AM</span>
                    </div>
                </div>
            </div>
        </div>
    
        </main>
    </div>
</template>

<script setup>
</script>

<style scoped>
</style>
