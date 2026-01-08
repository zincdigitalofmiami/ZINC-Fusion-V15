import Link from 'next/link'

export default function HomePage() {
  return (
    <>
      {/* Hero Section */}
      <section className="hero">
        <div className="hero-container">
          <div className="hero-content">
            <h1 className="hero-title">
              Institutional-Grade
              <br />
              Commodity Intelligence
            </h1>
            <p className="hero-subtitle">
              AI-powered soybean oil futures forecasting. Multi-horizon
              probabilistic models. Real-time regime detection.
            </p>
            <div className="hero-stats">
              <div className="stat-item">
                <div className="stat-number">4</div>
                <div className="stat-label">Horizons</div>
              </div>
              <div className="stat-item">
                <div className="stat-number">11</div>
                <div className="stat-label">Specialists</div>
              </div>
              <div className="stat-item">
                <div className="stat-number">87%</div>
                <div className="stat-label">Confidence</div>
              </div>
            </div>
          </div>
          <div className="hero-visual">
            <div className="data-cube">
              <div className="cube-face front">
                <div className="data-points">
                  <div className="data-point"></div>
                  <div className="data-point"></div>
                  <div className="data-point"></div>
                  <div className="data-point"></div>
                </div>
              </div>
              <div className="cube-face back"></div>
              <div className="cube-face right"></div>
              <div className="cube-face left"></div>
              <div className="cube-face top"></div>
              <div className="cube-face bottom"></div>
            </div>
          </div>
        </div>
      </section>

      {/* Intelligence Grid */}
      <section className="intelligence-grid">
        <div className="grid-container">
          <h2 className="section-title">Intelligence Modules</h2>
          <p className="section-subtitle">
            Eleven specialized models powering unified forecasts
          </p>
          <div className="intelligence-cards">
            <div className="intel-card core-card">
              <div className="card-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M3 3v18h18" />
                  <path d="M18.5 8l-5.5 5.5-3-3L6 14.5" />
                </svg>
              </div>
              <h3 className="card-title">Crush Spread</h3>
              <p className="card-description">
                Soy complex dynamics and processing margins
              </p>
              <div className="card-metrics">
                <div className="metric">
                  <span className="metric-value">28-35%</span>
                  <span className="metric-label">Weight</span>
                </div>
                <div className="metric">
                  <span className="metric-value">High</span>
                  <span className="metric-label">Signal</span>
                </div>
              </div>
            </div>

            <div className="intel-card">
              <div className="card-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <circle cx="12" cy="12" r="10" />
                  <path d="M2 12h20" />
                  <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10" />
                </svg>
              </div>
              <h3 className="card-title">China Demand</h3>
              <p className="card-description">
                Import dynamics and policy signals from China
              </p>
              <div className="card-metrics">
                <div className="metric">
                  <span className="metric-value">16-22%</span>
                  <span className="metric-label">Weight</span>
                </div>
                <div className="metric">
                  <span className="metric-value">Medium</span>
                  <span className="metric-label">Signal</span>
                </div>
              </div>
            </div>

            <div className="intel-card">
              <div className="card-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M12 2v20" />
                  <path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" />
                </svg>
              </div>
              <h3 className="card-title">FX / USD</h3>
              <p className="card-description">
                Dollar strength and EM currency impact
              </p>
              <div className="card-metrics">
                <div className="metric">
                  <span className="metric-value">3-5%</span>
                  <span className="metric-label">Weight</span>
                </div>
                <div className="metric">
                  <span className="metric-value">Low</span>
                  <span className="metric-label">Signal</span>
                </div>
              </div>
            </div>

            <div className="intel-card">
              <div className="card-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <rect x="3" y="3" width="18" height="18" rx="2" />
                  <path d="M3 9h18" />
                  <path d="M9 21V9" />
                </svg>
              </div>
              <h3 className="card-title">Fed Policy</h3>
              <p className="card-description">
                Interest rates and monetary policy signals
              </p>
              <div className="card-metrics">
                <div className="metric">
                  <span className="metric-value">2-4%</span>
                  <span className="metric-label">Weight</span>
                </div>
                <div className="metric">
                  <span className="metric-value">Low</span>
                  <span className="metric-label">Signal</span>
                </div>
              </div>
            </div>

            <div className="intel-card">
              <div className="card-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                </svg>
              </div>
              <h3 className="card-title">Energy</h3>
              <p className="card-description">
                Crude, natgas, and energy complex correlation
              </p>
              <div className="card-metrics">
                <div className="metric">
                  <span className="metric-value">10-14%</span>
                  <span className="metric-label">Weight</span>
                </div>
                <div className="metric">
                  <span className="metric-value">High</span>
                  <span className="metric-label">Signal</span>
                </div>
              </div>
            </div>

            <div className="intel-card">
              <div className="card-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                </svg>
              </div>
              <h3 className="card-title">Biofuel</h3>
              <p className="card-description">
                RFS, RINs, and biodiesel policy impact
              </p>
              <div className="card-metrics">
                <div className="metric">
                  <span className="metric-value">6-10%</span>
                  <span className="metric-label">Weight</span>
                </div>
                <div className="metric">
                  <span className="metric-value">High</span>
                  <span className="metric-label">Signal</span>
                </div>
              </div>
            </div>

            <div className="intel-card">
              <div className="card-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                </svg>
              </div>
              <h3 className="card-title">Palm Oil</h3>
              <p className="card-description">
                Malaysian palm and substitute dynamics
              </p>
              <div className="card-metrics">
                <div className="metric">
                  <span className="metric-value">8-12%</span>
                  <span className="metric-label">Weight</span>
                </div>
                <div className="metric">
                  <span className="metric-value">Medium</span>
                  <span className="metric-label">Signal</span>
                </div>
              </div>
            </div>

            <div className="intel-card">
              <div className="card-icon">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M14.5 10c-.83 0-1.5-.67-1.5-1.5v-5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5z" />
                  <path d="M20.5 10H19V8.5c0-.83.67-1.5 1.5-1.5s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z" />
                  <path d="M9.5 14c.83 0 1.5.67 1.5 1.5v5c0 .83-.67 1.5-1.5 1.5S8 21.33 8 20.5v-5c0-.83.67-1.5 1.5-1.5z" />
                  <path d="M3.5 14H5v1.5c0 .83-.67 1.5-1.5 1.5S2 16.33 2 15.5 2.67 14 3.5 14z" />
                  <path d="M14 14.5c0-.83.67-1.5 1.5-1.5h5c.83 0 1.5.67 1.5 1.5s-.67 1.5-1.5 1.5h-5c-.83 0-1.5-.67-1.5-1.5z" />
                  <path d="M14 20.5c0-.83.67-1.5 1.5-1.5H17v1.5c0 .83-.67 1.5-1.5 1.5s-1.5-.67-1.5-1.5z" />
                  <path d="M10 9.5C10 8.67 9.33 8 8.5 8h-5C2.67 8 2 8.67 2 9.5S2.67 11 3.5 11h5c.83 0 1.5-.67 1.5-1.5z" />
                  <path d="M8.5 5H10V3.5c0-.83-.67-1.5-1.5-1.5S7 2.67 7 3.5 7.67 5 8.5 5z" />
                </svg>
              </div>
              <h3 className="card-title">Volatility</h3>
              <p className="card-description">
                VIX regime and cross-asset vol dynamics
              </p>
              <div className="card-metrics">
                <div className="metric">
                  <span className="metric-value">2-3%</span>
                  <span className="metric-label">Weight</span>
                </div>
                <div className="metric">
                  <span className="metric-value">Low</span>
                  <span className="metric-label">Signal</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Signal Preview */}
      <section className="signal-preview">
        <div className="preview-container">
          <h2 className="preview-title">Current Signal</h2>
          <p className="preview-subtitle">
            Multi-horizon forecast with probabilistic confidence bands
          </p>
          <div className="signal-display">
            <div className="big-four-gauges">
              <div className="gauge-container">
                <div className="gauge-title">1 Week</div>
                <svg className="gauge-hz-svg" viewBox="0 0 120 70">
                  <defs>
                    <linearGradient id="gaugeGrad1" x1="0%" y1="0%" x2="100%" y2="0%">
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
                    stroke="url(#gaugeGrad1)"
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
                <div className="gauge-subtext">BUY</div>
                <div className="weight-contribution">$43.20 (+0.8%)</div>
              </div>

              <div className="gauge-container">
                <div className="gauge-title">1 Month</div>
                <svg className="gauge-hz-svg" viewBox="0 0 120 70">
                  <defs>
                    <linearGradient id="gaugeGrad2" x1="0%" y1="0%" x2="100%" y2="0%">
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
                    stroke="url(#gaugeGrad2)"
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
                <div className="gauge-subtext">BUY</div>
                <div className="weight-contribution">$44.10 (+2.9%)</div>
              </div>

              <div className="gauge-container">
                <div className="gauge-title">3 Month</div>
                <svg className="gauge-hz-svg" viewBox="0 0 120 70">
                  <defs>
                    <linearGradient id="gaugeGrad3" x1="0%" y1="0%" x2="100%" y2="0%">
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
                    stroke="url(#gaugeGrad3)"
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
                <div className="gauge-subtext">HOLD</div>
                <div className="weight-contribution">$42.50 (-0.8%)</div>
              </div>

              <div className="gauge-container">
                <div className="gauge-title">6 Month</div>
                <svg className="gauge-hz-svg" viewBox="0 0 120 70">
                  <defs>
                    <linearGradient id="gaugeGrad4" x1="0%" y1="0%" x2="100%" y2="0%">
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
                    stroke="url(#gaugeGrad4)"
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
                <div className="gauge-subtext">WAIT</div>
                <div className="weight-contribution">$41.80 (-2.5%)</div>
              </div>
            </div>

            <div className="current-signal">
              <div className="signal-item">
                <div className="signal-value" style={{ color: '#2962FF' }}>
                  BUY
                </div>
                <div className="signal-label">Composite Signal</div>
              </div>
              <div className="signal-item">
                <div className="signal-value">$42.85</div>
                <div className="signal-label">Current Price</div>
              </div>
              <div className="signal-item">
                <div className="signal-value" style={{ color: '#2962FF' }}>
                  +2.4%
                </div>
                <div className="signal-label">Expected Return</div>
              </div>
              <div className="signal-item">
                <div className="signal-value">87%</div>
                <div className="signal-label">Confidence</div>
              </div>
            </div>

            <Link href="/dashboard" className="view-dashboard-link">
              View Full Dashboard
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </Link>
          </div>
        </div>
      </section>

      {/* Primary Chart */}
      <section className="primary-chart">
        <div className="grid-container">
          <div className="chart-header">
            <div>
              <h3 className="chart-title">ZL Continuous — Soybean Oil</h3>
              <p className="chart-subtitle">
                Daily OHLCV with forecast overlay
              </p>
            </div>
            <div className="time-range-toggle">
              <button className="range-btn">1W</button>
              <button className="range-btn active">1M</button>
              <button className="range-btn">3M</button>
              <button className="range-btn">6M</button>
              <button className="range-btn">1Y</button>
            </div>
          </div>
          <Link href="/dashboard" className="chart-area">
            {/* Chart will be rendered here by lightweight-charts */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                height: '100%',
                opacity: 0.5,
              }}
            >
              Interactive chart — click to view dashboard
            </div>
            <div className="chart-cta">
              Click to expand
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M15 3h6v6M9 21H3v-6M21 3l-7 7M3 21l7-7" />
              </svg>
            </div>
          </Link>
        </div>
      </section>

      {/* CTA Section */}
      <section className="cta-section">
        <div className="cta-container">
          <h2 className="cta-title">Ready for Intelligence</h2>
          <p className="cta-description">
            Access real-time forecasts and procurement recommendations
          </p>
          <Link href="/dashboard" className="cta-button">
            Enter Dashboard
          </Link>
        </div>
      </section>

      {/* Footer */}
      <footer className="footer">
        <div className="footer-container">
          <p className="footer-text">
            © 2025 ZINC FUSION. Proprietary commodity intelligence system.
          </p>
        </div>
      </footer>
    </>
  )
}
