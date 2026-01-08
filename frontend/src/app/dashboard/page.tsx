import ZLPriceChart from '@/components/ZLPriceChart'

export default function DashboardPage() {
  return (
    <div className="main-content" style={{ maxWidth: '100%', padding: '0 24px' }}>
      {/* Full-width ZL Chart */}
      <div style={{ marginBottom: '32px' }}>
        <ZLPriceChart />
      </div>

      {/* Forecast Horizons - 4 cards equally spaced */}
      <div className="horizon-section" style={{ marginBottom: '32px' }}>
        <h4 className="horizon-title">Forecast Horizons</h4>
        <div className="horizon-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
          <div className="gauge-card-hz">
            <div className="gauge-hz-label">1 Week</div>
            <div className="gauge-hz-container">
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
                <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke="url(#gaugeGrad1)" strokeWidth="8" strokeLinecap="round" />
                <line x1="60" y1="60" x2="60" y2="20" stroke="white" strokeWidth="2" strokeLinecap="round" transform="rotate(45 60 60)" />
                <circle cx="60" cy="60" r="4" fill="white" />
              </svg>
            </div>
            <div className="gauge-hz-price">—</div>
            <div className="gauge-hz-change positive">—</div>
            <div className="gauge-hz-metrics">
              <div className="gauge-hz-metric"><span>P10</span><span>—</span></div>
              <div className="gauge-hz-metric"><span>P90</span><span>—</span></div>
            </div>
          </div>

          <div className="gauge-card-hz">
            <div className="gauge-hz-label">1 Month</div>
            <div className="gauge-hz-container">
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
                <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke="url(#gaugeGrad2)" strokeWidth="8" strokeLinecap="round" />
                <line x1="60" y1="60" x2="60" y2="20" stroke="white" strokeWidth="2" strokeLinecap="round" transform="rotate(30 60 60)" />
                <circle cx="60" cy="60" r="4" fill="white" />
              </svg>
            </div>
            <div className="gauge-hz-price">—</div>
            <div className="gauge-hz-change positive">—</div>
            <div className="gauge-hz-metrics">
              <div className="gauge-hz-metric"><span>P10</span><span>—</span></div>
              <div className="gauge-hz-metric"><span>P90</span><span>—</span></div>
            </div>
          </div>

          <div className="gauge-card-hz">
            <div className="gauge-hz-label">3 Month</div>
            <div className="gauge-hz-container">
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
                <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke="url(#gaugeGrad3)" strokeWidth="8" strokeLinecap="round" />
                <line x1="60" y1="60" x2="60" y2="20" stroke="white" strokeWidth="2" strokeLinecap="round" transform="rotate(-10 60 60)" />
                <circle cx="60" cy="60" r="4" fill="white" />
              </svg>
            </div>
            <div className="gauge-hz-price">—</div>
            <div className="gauge-hz-change negative">—</div>
            <div className="gauge-hz-metrics">
              <div className="gauge-hz-metric"><span>P10</span><span>—</span></div>
              <div className="gauge-hz-metric"><span>P90</span><span>—</span></div>
            </div>
          </div>

          <div className="gauge-card-hz">
            <div className="gauge-hz-label">6 Month</div>
            <div className="gauge-hz-container">
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
                <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke="url(#gaugeGrad4)" strokeWidth="8" strokeLinecap="round" />
                <line x1="60" y1="60" x2="60" y2="20" stroke="white" strokeWidth="2" strokeLinecap="round" transform="rotate(-30 60 60)" />
                <circle cx="60" cy="60" r="4" fill="white" />
              </svg>
            </div>
            <div className="gauge-hz-price">—</div>
            <div className="gauge-hz-change negative">—</div>
            <div className="gauge-hz-metrics">
              <div className="gauge-hz-metric"><span>P10</span><span>—</span></div>
              <div className="gauge-hz-metric"><span>P90</span><span>—</span></div>
            </div>
          </div>
        </div>
      </div>

      {/* Key Drivers - 4 gauges */}
      <div className="gauges-section">
        <h4 className="gauges-title">Key Drivers</h4>
        <div className="gauges-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
          <div className="gauge-card">
            <div className="gauge-label">Crush Spread</div>
            <div className="gauge-visual">
              <div className="gauge-arc"></div>
              <div className="gauge-needle" style={{ transform: 'rotate(30deg)' }}></div>
              <div className="gauge-center"></div>
            </div>
            <div className="gauge-value high">—</div>
            <div className="gauge-context">Soy processing margin<br />Supportive for ZL</div>
          </div>

          <div className="gauge-card">
            <div className="gauge-label">China Demand</div>
            <div className="gauge-visual">
              <div className="gauge-arc"></div>
              <div className="gauge-needle" style={{ transform: 'rotate(-10deg)' }}></div>
              <div className="gauge-center"></div>
            </div>
            <div className="gauge-value medium">—</div>
            <div className="gauge-context">Export sales activity<br />Neutral signal</div>
          </div>

          <div className="gauge-card">
            <div className="gauge-label">Volatility</div>
            <div className="gauge-visual">
              <div className="gauge-arc"></div>
              <div className="gauge-needle" style={{ transform: 'rotate(-20deg)' }}></div>
              <div className="gauge-center"></div>
            </div>
            <div className="gauge-value low">—</div>
            <div className="gauge-context">21-day realized vol<br />Low regime</div>
          </div>

          <div className="gauge-card">
            <div className="gauge-label">Palm Spread</div>
            <div className="gauge-visual">
              <div className="gauge-arc"></div>
              <div className="gauge-needle" style={{ transform: 'rotate(10deg)' }}></div>
              <div className="gauge-center"></div>
            </div>
            <div className="gauge-value medium">—</div>
            <div className="gauge-context">ZL vs palm premium<br />Substitution risk</div>
          </div>
        </div>
      </div>
    </div>
  )
}
