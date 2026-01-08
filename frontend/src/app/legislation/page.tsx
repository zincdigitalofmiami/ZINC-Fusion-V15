export default function LegislationPage() {
  return (
    <div className="main-content">
      <div className="page-header">
        <h1 className="page-title">Legislation</h1>
        <p className="page-subtitle">Policy calendar, bills, and executive orders</p>
      </div>

      {/* Alert Banner */}
      <div className="alert-banner" style={{ marginBottom: '32px' }}>
        <svg
          className="alert-banner-icon"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="12" y1="8" x2="12" y2="12" />
          <line x1="12" y1="16" x2="12.01" y2="16" />
        </svg>
        <div className="alert-banner-text">
          <span className="alert-banner-highlight">EPA RFS RVO Decision</span>
          {' '} — Final rule expected Jan 15, 2025. High impact on biofuel demand.
        </div>
        <div className="alert-banner-tags">
          <span className="alert-tag">BIOFUEL</span>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
        {/* Main Calendar/Timeline */}
        <div>
          {/* Upcoming Events */}
          <div className="card" style={{ marginBottom: '24px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '24px' }}>Upcoming Policy Events</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Event 1 */}
              <div style={{ display: 'flex', gap: '16px', padding: '20px', background: 'rgba(239, 83, 80, 0.1)', border: '1px solid rgba(239, 83, 80, 0.3)', borderRadius: '12px' }}>
                <div style={{ textAlign: 'center', minWidth: '60px' }}>
                  <div style={{ fontSize: '24px', fontWeight: 700 }}>15</div>
                  <div style={{ fontSize: '12px', opacity: 0.6 }}>JAN</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <span style={{ fontWeight: 600 }}>EPA RFS Final RVO Rule</span>
                    <span className="badge badge-negative">HIGH IMPACT</span>
                  </div>
                  <div style={{ fontSize: '13px', opacity: 0.7, marginBottom: '12px' }}>
                    Final renewable volume obligations for 2025-2027. Expected increase in biodiesel mandate.
                    Directly impacts soybean oil demand for biofuel production.
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <span className="badge badge-neutral">BIOFUEL</span>
                    <span className="badge badge-neutral">EPA</span>
                  </div>
                </div>
              </div>

              {/* Event 2 */}
              <div style={{ display: 'flex', gap: '16px', padding: '20px', background: 'rgba(255, 180, 100, 0.08)', border: '1px solid rgba(255, 180, 100, 0.3)', borderRadius: '12px' }}>
                <div style={{ textAlign: 'center', minWidth: '60px' }}>
                  <div style={{ fontSize: '24px', fontWeight: 700 }}>20</div>
                  <div style={{ fontSize: '12px', opacity: 0.6 }}>JAN</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <span style={{ fontWeight: 600 }}>Trump Inauguration Day</span>
                    <span className="badge badge-warning">MED IMPACT</span>
                  </div>
                  <div style={{ fontSize: '13px', opacity: 0.7, marginBottom: '12px' }}>
                    Potential immediate executive orders on trade, tariffs, and energy policy.
                    Watch for China trade rhetoric and biofuel policy signals.
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <span className="badge badge-neutral">TRUMP EFFECT</span>
                    <span className="badge badge-neutral">TARIFF</span>
                  </div>
                </div>
              </div>

              {/* Event 3 */}
              <div style={{ display: 'flex', gap: '16px', padding: '20px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '12px' }}>
                <div style={{ textAlign: 'center', minWidth: '60px' }}>
                  <div style={{ fontSize: '24px', fontWeight: 700 }}>29</div>
                  <div style={{ fontSize: '12px', opacity: 0.6 }}>JAN</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <span style={{ fontWeight: 600 }}>FOMC Rate Decision</span>
                    <span className="badge badge-neutral">LOW IMPACT</span>
                  </div>
                  <div style={{ fontSize: '13px', opacity: 0.7, marginBottom: '12px' }}>
                    Federal Reserve interest rate decision. Expected hold. Dollar implications for commodity prices.
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <span className="badge badge-neutral">FED</span>
                    <span className="badge badge-neutral">FX</span>
                  </div>
                </div>
              </div>

              {/* Event 4 */}
              <div style={{ display: 'flex', gap: '16px', padding: '20px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '12px' }}>
                <div style={{ textAlign: 'center', minWidth: '60px' }}>
                  <div style={{ fontSize: '24px', fontWeight: 700 }}>10</div>
                  <div style={{ fontSize: '12px', opacity: 0.6 }}>FEB</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                    <span style={{ fontWeight: 600 }}>USDA WASDE Report</span>
                    <span className="badge badge-warning">MED IMPACT</span>
                  </div>
                  <div style={{ fontSize: '13px', opacity: 0.7, marginBottom: '12px' }}>
                    Monthly World Agricultural Supply and Demand Estimates. South America crop updates.
                  </div>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <span className="badge badge-neutral">USDA</span>
                    <span className="badge badge-neutral">SUPPLY</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Active Bills */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '24px' }}>Active Bills & Legislation</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>H.R. 1234 — Renewable Fuel Standard Reform Act</div>
                  <div style={{ fontSize: '12px', opacity: 0.6 }}>House Energy & Commerce Committee</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '12px', opacity: 0.6, marginBottom: '4px' }}>Status</div>
                  <div style={{ padding: '4px 12px', background: 'rgba(255, 180, 100, 0.2)', borderRadius: '4px', fontSize: '11px', fontWeight: 600, color: '#ffb464' }}>IN COMMITTEE</div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>S. 567 — Agricultural Trade Fairness Act</div>
                  <div style={{ fontSize: '12px', opacity: 0.6 }}>Senate Agriculture Committee</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '12px', opacity: 0.6, marginBottom: '4px' }}>Status</div>
                  <div style={{ padding: '4px 12px', background: 'rgba(41, 98, 255, 0.2)', borderRadius: '4px', fontSize: '11px', fontWeight: 600, color: '#2962FF' }}>PASSED SENATE</div>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>H.R. 890 — China Tariff Extension Act</div>
                  <div style={{ fontSize: '12px', opacity: 0.6 }}>House Ways & Means Committee</div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '12px', opacity: 0.6, marginBottom: '4px' }}>Status</div>
                  <div style={{ padding: '4px 12px', background: 'rgba(255, 255, 255, 0.1)', borderRadius: '4px', fontSize: '11px', fontWeight: 600, opacity: 0.6 }}>INTRODUCED</div>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Executive Orders */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Recent Executive Orders</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ padding: '16px', background: 'rgba(239, 83, 80, 0.1)', border: '1px solid rgba(239, 83, 80, 0.3)', borderRadius: '8px' }}>
                <div style={{ fontSize: '11px', opacity: 0.5, marginBottom: '8px' }}>Expected Jan 20</div>
                <div style={{ fontWeight: 600, marginBottom: '8px', color: '#ef5350' }}>China Trade Review EO</div>
                <div style={{ fontSize: '12px', opacity: 0.7 }}>
                  Expected executive order reviewing all China trade agreements. High uncertainty.
                </div>
              </div>
              <div style={{ padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px' }}>
                <div style={{ fontSize: '11px', opacity: 0.5, marginBottom: '8px' }}>Dec 15, 2024</div>
                <div style={{ fontWeight: 600, marginBottom: '8px' }}>EO 14567 — Energy Independence</div>
                <div style={{ fontSize: '12px', opacity: 0.7 }}>
                  Review of renewable energy mandates. Biofuel policy under review.
                </div>
              </div>
            </div>
          </div>

          {/* Policy Impact Summary */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Policy Impact Summary</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <span style={{ fontSize: '13px', opacity: 0.7 }}>Biofuel Policy</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#2962FF' }}>BULLISH</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <span style={{ fontSize: '13px', opacity: 0.7 }}>Trade/Tariffs</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#ef5350' }}>UNCERTAIN</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0', borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <span style={{ fontSize: '13px', opacity: 0.7 }}>Fed Policy</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#787B86' }}>NEUTRAL</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', padding: '8px 0' }}>
                <span style={{ fontSize: '13px', opacity: 0.7 }}>Ag Subsidies</span>
                <span style={{ fontSize: '13px', fontWeight: 600, color: '#2962FF' }}>SUPPORTIVE</span>
              </div>
            </div>
          </div>

          {/* Quick Stats */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Tracked Metrics</h3>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '28px', fontWeight: 700, color: '#ef5350' }}>187</div>
                <div style={{ fontSize: '11px', opacity: 0.5 }}>EPU Index</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '28px', fontWeight: 700 }}>12</div>
                <div style={{ fontSize: '11px', opacity: 0.5 }}>Active Bills</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '28px', fontWeight: 700, color: '#ffb464' }}>3</div>
                <div style={{ fontSize: '11px', opacity: 0.5 }}>High Impact</div>
              </div>
              <div style={{ textAlign: 'center' }}>
                <div style={{ fontSize: '28px', fontWeight: 700 }}>7d</div>
                <div style={{ fontSize: '11px', opacity: 0.5 }}>Next Event</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
