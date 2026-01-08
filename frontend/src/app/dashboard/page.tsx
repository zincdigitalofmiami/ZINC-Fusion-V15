export default function DashboardPage() {
  return (
    <div className="main-content">
      {/* Alert Banner */}
      <div className="alert-banner">
        <svg
          className="alert-banner-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <div className="alert-banner-text">
          <span className="alert-banner-highlight">China trade policy uncertainty elevated</span>
          {' '} — EPU Index at 187 (vs 125 avg). Consider accelerating near-term procurement.
        </div>
        <div className="alert-banner-tags">
          <span className="alert-tag">TARIFF RISK</span>
          <span className="alert-tag">TRUMP EFFECT</span>
        </div>
      </div>

      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">Real-time forecast analytics and signals</p>
      </div>

      <div className="dashboard-grid">
        {/* Main Content */}
        <div className="main-col">
          {/* Chart Section */}
          <div className="chart-section">
            <div className="chart-header">
              <div>
                <h3 className="chart-title">ZL Continuous — Soybean Oil</h3>
                <p className="chart-subtitle">Daily OHLCV with forecast bands</p>
              </div>
              <div className="time-range-selector">
                <button className="range-btn">1W</button>
                <button className="range-btn active">1M</button>
                <button className="range-btn">3M</button>
                <button className="range-btn">6M</button>
                <button className="range-btn">1Y</button>
                <button className="range-btn">ALL</button>
              </div>
            </div>
            <div className="chart-container" id="zl-chart">
              {/* lightweight-charts will render here */}
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  height: '100%',
                  opacity: 0.4,
                  fontSize: '14px',
                }}
              >
                Chart renders with lightweight-charts
              </div>
            </div>
          </div>

          {/* Horizon Gauge Cards */}
          <div className="horizon-section">
            <h4 className="horizon-title">Forecast Horizons</h4>
            <div className="horizon-grid">
              <div className="gauge-card-hz">
                <div className="gauge-hz-label">1 Week</div>
                <div className="gauge-hz-container">
                  <svg className="gauge-hz-svg" viewBox="0 0 120 70">
                    <defs>
                      <linearGradient id="gaugeGradDash1" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#ef5350" />
                        <stop offset="25%" stopColor="#ffb74d" />
                        <stop offset="50%" stopColor="#ffd54f" />
                        <stop offset="75%" stopColor="#81c784" />
                        <stop offset="100%" stopColor="#2962FF" />
                      </linearGradient>
                    </defs>
                    <path
                      d="M 10 60 A 50 50 0 0 1 110 60"
                      fill="none"
                      stroke="url(#gaugeGradDash1)"
                      strokeWidth="8"
                      strokeLinecap="round"
                    />
                    <line
                      x1="60"
                      y1="60"
                      x2="60"
                      y2="20"
                      stroke="white"
                      strokeWidth="2"
                      strokeLinecap="round"
                      transform="rotate(45 60 60)"
                    />
                    <circle cx="60" cy="60" r="4" fill="white" />
                  </svg>
                </div>
                <div className="gauge-hz-price">$43.20</div>
                <div className="gauge-hz-change positive">+0.8%</div>
                <div className="gauge-hz-metrics">
                  <div className="gauge-hz-metric">
                    <span>P10</span>
                    <span>$42.50</span>
                  </div>
                  <div className="gauge-hz-metric">
                    <span>P90</span>
                    <span>$44.10</span>
                  </div>
                </div>
              </div>

              <div className="gauge-card-hz">
                <div className="gauge-hz-label">1 Month</div>
                <div className="gauge-hz-container">
                  <svg className="gauge-hz-svg" viewBox="0 0 120 70">
                    <defs>
                      <linearGradient id="gaugeGradDash2" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#ef5350" />
                        <stop offset="25%" stopColor="#ffb74d" />
                        <stop offset="50%" stopColor="#ffd54f" />
                        <stop offset="75%" stopColor="#81c784" />
                        <stop offset="100%" stopColor="#2962FF" />
                      </linearGradient>
                    </defs>
                    <path
                      d="M 10 60 A 50 50 0 0 1 110 60"
                      fill="none"
                      stroke="url(#gaugeGradDash2)"
                      strokeWidth="8"
                      strokeLinecap="round"
                    />
                    <line
                      x1="60"
                      y1="60"
                      x2="60"
                      y2="20"
                      stroke="white"
                      strokeWidth="2"
                      strokeLinecap="round"
                      transform="rotate(30 60 60)"
                    />
                    <circle cx="60" cy="60" r="4" fill="white" />
                  </svg>
                </div>
                <div className="gauge-hz-price">$44.10</div>
                <div className="gauge-hz-change positive">+2.9%</div>
                <div className="gauge-hz-metrics">
                  <div className="gauge-hz-metric">
                    <span>P10</span>
                    <span>$41.80</span>
                  </div>
                  <div className="gauge-hz-metric">
                    <span>P90</span>
                    <span>$46.50</span>
                  </div>
                </div>
              </div>

              <div className="gauge-card-hz">
                <div className="gauge-hz-label">3 Month</div>
                <div className="gauge-hz-container">
                  <svg className="gauge-hz-svg" viewBox="0 0 120 70">
                    <defs>
                      <linearGradient id="gaugeGradDash3" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#ef5350" />
                        <stop offset="25%" stopColor="#ffb74d" />
                        <stop offset="50%" stopColor="#ffd54f" />
                        <stop offset="75%" stopColor="#81c784" />
                        <stop offset="100%" stopColor="#2962FF" />
                      </linearGradient>
                    </defs>
                    <path
                      d="M 10 60 A 50 50 0 0 1 110 60"
                      fill="none"
                      stroke="url(#gaugeGradDash3)"
                      strokeWidth="8"
                      strokeLinecap="round"
                    />
                    <line
                      x1="60"
                      y1="60"
                      x2="60"
                      y2="20"
                      stroke="white"
                      strokeWidth="2"
                      strokeLinecap="round"
                      transform="rotate(-10 60 60)"
                    />
                    <circle cx="60" cy="60" r="4" fill="white" />
                  </svg>
                </div>
                <div className="gauge-hz-price">$42.50</div>
                <div className="gauge-hz-change negative">-0.8%</div>
                <div className="gauge-hz-metrics">
                  <div className="gauge-hz-metric">
                    <span>P10</span>
                    <span>$39.20</span>
                  </div>
                  <div className="gauge-hz-metric">
                    <span>P90</span>
                    <span>$47.80</span>
                  </div>
                </div>
              </div>

              <div className="gauge-card-hz">
                <div className="gauge-hz-label">6 Month</div>
                <div className="gauge-hz-container">
                  <svg className="gauge-hz-svg" viewBox="0 0 120 70">
                    <defs>
                      <linearGradient id="gaugeGradDash4" x1="0%" y1="0%" x2="100%" y2="0%">
                        <stop offset="0%" stopColor="#ef5350" />
                        <stop offset="25%" stopColor="#ffb74d" />
                        <stop offset="50%" stopColor="#ffd54f" />
                        <stop offset="75%" stopColor="#81c784" />
                        <stop offset="100%" stopColor="#2962FF" />
                      </linearGradient>
                    </defs>
                    <path
                      d="M 10 60 A 50 50 0 0 1 110 60"
                      fill="none"
                      stroke="url(#gaugeGradDash4)"
                      strokeWidth="8"
                      strokeLinecap="round"
                    />
                    <line
                      x1="60"
                      y1="60"
                      x2="60"
                      y2="20"
                      stroke="white"
                      strokeWidth="2"
                      strokeLinecap="round"
                      transform="rotate(-30 60 60)"
                    />
                    <circle cx="60" cy="60" r="4" fill="white" />
                  </svg>
                </div>
                <div className="gauge-hz-price">$41.80</div>
                <div className="gauge-hz-change negative">-2.5%</div>
                <div className="gauge-hz-metrics">
                  <div className="gauge-hz-metric">
                    <span>P10</span>
                    <span>$36.50</span>
                  </div>
                  <div className="gauge-hz-metric">
                    <span>P90</span>
                    <span>$49.20</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Gauges Section */}
          <div className="gauges-section">
            <h4 className="gauges-title">Risk Gauges</h4>
            <div className="gauges-grid">
              <div className="gauge-card">
                <div className="gauge-label">VIX</div>
                <div className="gauge-visual">
                  <div className="gauge-arc"></div>
                  <div className="gauge-needle" style={{ transform: 'rotate(-45deg)' }}></div>
                  <div className="gauge-center"></div>
                </div>
                <div className="gauge-value low">14.2</div>
                <div className="gauge-context">Low volatility regime<br />Risk appetite elevated</div>
              </div>

              <div className="gauge-card">
                <div className="gauge-label">OVX</div>
                <div className="gauge-visual">
                  <div className="gauge-arc"></div>
                  <div className="gauge-needle" style={{ transform: 'rotate(-20deg)' }}></div>
                  <div className="gauge-center"></div>
                </div>
                <div className="gauge-value medium">28.5</div>
                <div className="gauge-context">Moderate oil vol<br />Watch energy spreads</div>
              </div>

              <div className="gauge-card">
                <div className="gauge-label">EPU Index</div>
                <div className="gauge-visual">
                  <div className="gauge-arc"></div>
                  <div className="gauge-needle" style={{ transform: 'rotate(30deg)' }}></div>
                  <div className="gauge-center"></div>
                </div>
                <div className="gauge-value high">187</div>
                <div className="gauge-context">Policy uncertainty high<br />Trump effect active</div>
              </div>

              <div className="gauge-card">
                <div className="gauge-label">DXY</div>
                <div className="gauge-visual">
                  <div className="gauge-arc"></div>
                  <div className="gauge-needle" style={{ transform: 'rotate(10deg)' }}></div>
                  <div className="gauge-center"></div>
                </div>
                <div className="gauge-value medium">104.2</div>
                <div className="gauge-context">Dollar strength<br />Headwind for commodities</div>
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div className="sidebar">
          {/* Posture Card */}
          <div className="posture-card">
            <div className="posture-label">Current Posture</div>
            <div className="posture-value buy">BUY</div>
            <p className="posture-reason">
              Near-term bullish bias from crush spread compression and biofuel
              mandate support. Tactically favor 1W-1M exposure.
            </p>
          </div>

          {/* Signals Card */}
          <div className="signals-card">
            <h4 className="signals-title">Specialist Signals</h4>
            <div className="signal-row">
              <span className="signal-name">Crush Spread</span>
              <span className="signal-value positive">+2.1σ</span>
              <div className="signal-bar">
                <div className="signal-bar-fill positive" style={{ width: '70%' }}></div>
              </div>
            </div>
            <div className="signal-row">
              <span className="signal-name">China Demand</span>
              <span className="signal-value neutral">+0.3σ</span>
              <div className="signal-bar">
                <div className="signal-bar-fill positive" style={{ width: '15%' }}></div>
              </div>
            </div>
            <div className="signal-row">
              <span className="signal-name">Energy</span>
              <span className="signal-value positive">+1.4σ</span>
              <div className="signal-bar">
                <div className="signal-bar-fill positive" style={{ width: '50%' }}></div>
              </div>
            </div>
            <div className="signal-row">
              <span className="signal-name">Biofuel</span>
              <span className="signal-value positive">+1.8σ</span>
              <div className="signal-bar">
                <div className="signal-bar-fill positive" style={{ width: '60%' }}></div>
              </div>
            </div>
            <div className="signal-row">
              <span className="signal-name">Palm</span>
              <span className="signal-value negative">-0.8σ</span>
              <div className="signal-bar">
                <div className="signal-bar-fill negative" style={{ width: '30%' }}></div>
              </div>
            </div>
            <div className="signal-row">
              <span className="signal-name">FX / USD</span>
              <span className="signal-value negative">-0.5σ</span>
              <div className="signal-bar">
                <div className="signal-bar-fill negative" style={{ width: '20%' }}></div>
              </div>
            </div>
            <div className="signal-row">
              <span className="signal-name">Trump Effect</span>
              <span className="signal-value neutral">+0.2σ</span>
              <div className="signal-bar">
                <div className="signal-bar-fill positive" style={{ width: '10%' }}></div>
              </div>
            </div>
          </div>

          {/* Metrics Card */}
          <div className="metrics-card">
            <h4 className="metrics-title">Model Metrics</h4>
            <div className="metric-row">
              <span className="metric-label">Last Update</span>
              <span className="metric-value">2025-01-06 08:30</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Model Version</span>
              <span className="metric-value">v15.2.1</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Data Freshness</span>
              <span className="metric-value" style={{ color: '#81c784' }}>Live</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">P50 MAE (5d)</span>
              <span className="metric-value">0.42%</span>
            </div>
            <div className="metric-row">
              <span className="metric-label">Coverage (P10-P90)</span>
              <span className="metric-value">84.2%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
