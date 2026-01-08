export default function StrategyPage() {
  return (
    <div className="main-content">
      <div className="page-header">
        <h1 className="page-title">Strategy</h1>
        <p className="page-subtitle">Procurement posture and horizon analysis</p>
      </div>

      {/* Posture Section */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '24px', marginBottom: '40px' }}>
        {/* Main Posture Card */}
        <div className="card-elevated" style={{ textAlign: 'center', padding: '40px' }}>
          <div style={{ fontSize: '12px', opacity: 0.6, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '16px' }}>
            Current Posture
          </div>
          <div style={{ fontSize: '64px', fontWeight: 700, color: '#2962FF', marginBottom: '16px', letterSpacing: '2px' }}>
            BUY
          </div>
          <div style={{ fontSize: '14px', opacity: 0.7, lineHeight: 1.6, maxWidth: '280px', margin: '0 auto' }}>
            Near-term bullish bias from crush spread compression and biofuel mandate support.
            Tactically favor 1W-1M exposure.
          </div>
          <div style={{ marginTop: '24px', paddingTop: '24px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
            <div style={{ display: 'flex', justifyContent: 'center', gap: '32px' }}>
              <div>
                <div style={{ fontSize: '24px', fontWeight: 700 }}>87%</div>
                <div style={{ fontSize: '11px', opacity: 0.5 }}>Confidence</div>
              </div>
              <div>
                <div style={{ fontSize: '24px', fontWeight: 700, color: '#2962FF' }}>+2.4%</div>
                <div style={{ fontSize: '11px', opacity: 0.5 }}>Expected</div>
              </div>
            </div>
          </div>
        </div>

        {/* Horizon Analysis */}
        <div className="card" style={{ padding: '24px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Horizon Analysis</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '16px' }}>
            <div className="horizon-card bullish">
              <div className="horizon-period">1 Week</div>
              <div className="horizon-price">$43.20</div>
              <div className="horizon-change positive">+0.8%</div>
              <div className="horizon-range">$42.50 – $44.10</div>
              <div className="horizon-confidence">92% Conf</div>
            </div>
            <div className="horizon-card bullish">
              <div className="horizon-period">1 Month</div>
              <div className="horizon-price">$44.10</div>
              <div className="horizon-change positive">+2.9%</div>
              <div className="horizon-range">$41.80 – $46.50</div>
              <div className="horizon-confidence">85% Conf</div>
            </div>
            <div className="horizon-card">
              <div className="horizon-period">3 Month</div>
              <div className="horizon-price">$42.50</div>
              <div className="horizon-change negative">-0.8%</div>
              <div className="horizon-range">$39.20 – $47.80</div>
              <div className="horizon-confidence">72% Conf</div>
            </div>
            <div className="horizon-card bearish">
              <div className="horizon-period">6 Month</div>
              <div className="horizon-price">$41.80</div>
              <div className="horizon-change negative">-2.5%</div>
              <div className="horizon-range">$36.50 – $49.20</div>
              <div className="horizon-confidence">64% Conf</div>
            </div>
          </div>
        </div>
      </div>

      {/* Scenario Analysis */}
      <div className="card" style={{ marginBottom: '24px' }}>
        <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Scenario Analysis</h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '24px' }}>
          {/* Bull Case */}
          <div style={{ background: 'rgba(41, 98, 255, 0.08)', border: '1px solid rgba(41, 98, 255, 0.3)', borderRadius: '12px', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#2962FF' }}></div>
              <span style={{ fontSize: '14px', fontWeight: 600, color: '#2962FF' }}>Bull Case</span>
              <span style={{ marginLeft: 'auto', fontSize: '12px', opacity: 0.6 }}>25% Prob</span>
            </div>
            <div style={{ fontSize: '32px', fontWeight: 700, marginBottom: '8px' }}>$48.50</div>
            <div style={{ fontSize: '14px', color: '#2962FF', marginBottom: '16px' }}>+13.2%</div>
            <ul style={{ fontSize: '12px', opacity: 0.7, lineHeight: 1.6, listStyle: 'none' }}>
              <li>• China demand surge</li>
              <li>• Biofuel mandate expansion</li>
              <li>• La Niña crop stress</li>
              <li>• USD weakness</li>
            </ul>
          </div>

          {/* Base Case */}
          <div style={{ background: 'rgba(255, 255, 255, 0.05)', border: '1px solid rgba(255, 255, 255, 0.2)', borderRadius: '12px', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#787B86' }}></div>
              <span style={{ fontSize: '14px', fontWeight: 600 }}>Base Case</span>
              <span style={{ marginLeft: 'auto', fontSize: '12px', opacity: 0.6 }}>50% Prob</span>
            </div>
            <div style={{ fontSize: '32px', fontWeight: 700, marginBottom: '8px' }}>$43.85</div>
            <div style={{ fontSize: '14px', color: '#787B86', marginBottom: '16px' }}>+2.3%</div>
            <ul style={{ fontSize: '12px', opacity: 0.7, lineHeight: 1.6, listStyle: 'none' }}>
              <li>• Steady crush margins</li>
              <li>• Normal China imports</li>
              <li>• Stable energy prices</li>
              <li>• Range-bound FX</li>
            </ul>
          </div>

          {/* Bear Case */}
          <div style={{ background: 'rgba(239, 83, 80, 0.08)', border: '1px solid rgba(239, 83, 80, 0.3)', borderRadius: '12px', padding: '24px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '16px' }}>
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#ef5350' }}></div>
              <span style={{ fontSize: '14px', fontWeight: 600, color: '#ef5350' }}>Bear Case</span>
              <span style={{ marginLeft: 'auto', fontSize: '12px', opacity: 0.6 }}>25% Prob</span>
            </div>
            <div style={{ fontSize: '32px', fontWeight: 700, marginBottom: '8px' }}>$38.20</div>
            <div style={{ fontSize: '14px', color: '#ef5350', marginBottom: '16px' }}>-10.9%</div>
            <ul style={{ fontSize: '12px', opacity: 0.7, lineHeight: 1.6, listStyle: 'none' }}>
              <li>• Trade war escalation</li>
              <li>• Record S. America crop</li>
              <li>• Biofuel policy reversal</li>
              <li>• Global demand slump</li>
            </ul>
          </div>
        </div>
      </div>

      {/* Recommendations Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        {/* Tactical Actions */}
        <div className="card">
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Tactical Actions</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', padding: '16px', background: 'rgba(41, 98, 255, 0.1)', border: '1px solid rgba(41, 98, 255, 0.3)', borderRadius: '8px' }}>
              <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'rgba(41, 98, 255, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginRight: '16px' }}>
                <span style={{ color: '#2962FF', fontWeight: 700 }}>1</span>
              </div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: '4px' }}>Accelerate Q1 Coverage</div>
                <div style={{ fontSize: '12px', opacity: 0.6 }}>Lock 60% of Q1 needs at current levels</div>
              </div>
              <div style={{ marginLeft: 'auto', padding: '4px 12px', background: 'rgba(41, 98, 255, 0.2)', borderRadius: '4px', fontSize: '11px', fontWeight: 600, color: '#2962FF' }}>HIGH</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px' }}>
              <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'rgba(255, 255, 255, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginRight: '16px' }}>
                <span style={{ fontWeight: 700 }}>2</span>
              </div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: '4px' }}>Monitor China Signals</div>
                <div style={{ fontSize: '12px', opacity: 0.6 }}>Watch USDA export sales and port activity</div>
              </div>
              <div style={{ marginLeft: 'auto', padding: '4px 12px', background: 'rgba(255, 180, 100, 0.2)', borderRadius: '4px', fontSize: '11px', fontWeight: 600, color: '#ffb464' }}>MED</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px' }}>
              <div style={{ width: '32px', height: '32px', borderRadius: '8px', background: 'rgba(255, 255, 255, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', marginRight: '16px' }}>
                <span style={{ fontWeight: 700 }}>3</span>
              </div>
              <div>
                <div style={{ fontWeight: 600, marginBottom: '4px' }}>Defer H2 Decisions</div>
                <div style={{ fontSize: '12px', opacity: 0.6 }}>Wait for WASDE and South America harvest</div>
              </div>
              <div style={{ marginLeft: 'auto', padding: '4px 12px', background: 'rgba(255, 255, 255, 0.1)', borderRadius: '4px', fontSize: '11px', fontWeight: 600, opacity: 0.6 }}>LOW</div>
            </div>
          </div>
        </div>

        {/* Risk Factors */}
        <div className="card">
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Active Risk Factors</h3>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', background: 'rgba(239, 83, 80, 0.1)', border: '1px solid rgba(239, 83, 80, 0.3)', borderRadius: '8px' }}>
              <div>
                <div style={{ fontWeight: 600, color: '#ef5350', marginBottom: '4px' }}>Trump Tariff Threat</div>
                <div style={{ fontSize: '12px', opacity: 0.6 }}>EPU Index elevated at 187</div>
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#ef5350' }}>HIGH</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', background: 'rgba(255, 180, 100, 0.08)', border: '1px solid rgba(255, 180, 100, 0.3)', borderRadius: '8px' }}>
              <div>
                <div style={{ fontWeight: 600, color: '#ffb464', marginBottom: '4px' }}>Brazil Crop Progress</div>
                <div style={{ fontSize: '12px', opacity: 0.6 }}>Early harvest concerns</div>
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#ffb464' }}>MED</div>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px' }}>
              <div>
                <div style={{ fontWeight: 600, marginBottom: '4px' }}>Fed Rate Decision</div>
                <div style={{ fontSize: '12px', opacity: 0.6 }}>Next meeting Jan 29</div>
              </div>
              <div style={{ fontSize: '24px', fontWeight: 700, opacity: 0.5 }}>LOW</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
