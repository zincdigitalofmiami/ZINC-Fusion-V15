export default function SentimentPage() {
  return (
    <div className="main-content">
      <div className="page-header">
        <h1 className="page-title">Sentiment</h1>
        <p className="page-subtitle">Market sentiment and specialist breakdown</p>
      </div>

      {/* Composite Sentiment */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '24px', marginBottom: '40px' }}>
        <div className="card-elevated" style={{ textAlign: 'center', padding: '40px' }}>
          <div style={{ fontSize: '12px', opacity: 0.6, textTransform: 'uppercase', letterSpacing: '1px', marginBottom: '16px' }}>
            Composite Sentiment
          </div>
          <div style={{ fontSize: '64px', fontWeight: 700, color: '#2962FF', marginBottom: '16px' }}>
            +0.72
          </div>
          <div style={{ fontSize: '14px', opacity: 0.7, marginBottom: '24px' }}>
            Bullish bias across specialists
          </div>
          <div style={{ display: 'flex', justifyContent: 'center', gap: '24px', paddingTop: '24px', borderTop: '1px solid rgba(255,255,255,0.1)' }}>
            <div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#2962FF' }}>7</div>
              <div style={{ fontSize: '11px', opacity: 0.5 }}>Bullish</div>
            </div>
            <div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#787B86' }}>2</div>
              <div style={{ fontSize: '11px', opacity: 0.5 }}>Neutral</div>
            </div>
            <div>
              <div style={{ fontSize: '20px', fontWeight: 700, color: '#ef5350' }}>2</div>
              <div style={{ fontSize: '11px', opacity: 0.5 }}>Bearish</div>
            </div>
          </div>
        </div>

        {/* Specialist Breakdown Grid */}
        <div className="card">
          <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Specialist Breakdown</h3>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px' }}>
            <div style={{ padding: '16px', background: 'rgba(41, 98, 255, 0.1)', border: '1px solid rgba(41, 98, 255, 0.3)', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px' }}>Crush</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#2962FF' }}>+2.1σ</div>
              <div style={{ fontSize: '11px', marginTop: '8px', color: '#2962FF' }}>Strong Buy</div>
            </div>
            <div style={{ padding: '16px', background: 'rgba(41, 98, 255, 0.08)', border: '1px solid rgba(41, 98, 255, 0.2)', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px' }}>Biofuel</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#2962FF' }}>+1.8σ</div>
              <div style={{ fontSize: '11px', marginTop: '8px', color: '#2962FF' }}>Buy</div>
            </div>
            <div style={{ padding: '16px', background: 'rgba(41, 98, 255, 0.05)', border: '1px solid rgba(41, 98, 255, 0.15)', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px' }}>Energy</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#2962FF' }}>+1.4σ</div>
              <div style={{ fontSize: '11px', marginTop: '8px', color: '#2962FF' }}>Buy</div>
            </div>
            <div style={{ padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px' }}>China</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#787B86' }}>+0.3σ</div>
              <div style={{ fontSize: '11px', marginTop: '8px', opacity: 0.6 }}>Neutral</div>
            </div>
            <div style={{ padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px' }}>Trump Effect</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#787B86' }}>+0.2σ</div>
              <div style={{ fontSize: '11px', marginTop: '8px', opacity: 0.6 }}>Neutral</div>
            </div>
            <div style={{ padding: '16px', background: 'rgba(239, 83, 80, 0.05)', border: '1px solid rgba(239, 83, 80, 0.15)', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px' }}>FX / USD</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#ef5350' }}>-0.5σ</div>
              <div style={{ fontSize: '11px', marginTop: '8px', color: '#ef5350' }}>Weak Sell</div>
            </div>
            <div style={{ padding: '16px', background: 'rgba(239, 83, 80, 0.08)', border: '1px solid rgba(239, 83, 80, 0.2)', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px' }}>Palm</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#ef5350' }}>-0.8σ</div>
              <div style={{ fontSize: '11px', marginTop: '8px', color: '#ef5350' }}>Sell</div>
            </div>
            <div style={{ padding: '16px', background: 'rgba(41, 98, 255, 0.03)', border: '1px solid rgba(41, 98, 255, 0.1)', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px' }}>Volatility</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#2962FF' }}>+0.6σ</div>
              <div style={{ fontSize: '11px', marginTop: '8px', color: '#2962FF' }}>Weak Buy</div>
            </div>
            <div style={{ padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px', textAlign: 'center' }}>
              <div style={{ fontSize: '11px', opacity: 0.6, marginBottom: '8px' }}>Fed</div>
              <div style={{ fontSize: '24px', fontWeight: 700, color: '#787B86' }}>+0.1σ</div>
              <div style={{ fontSize: '11px', marginTop: '8px', opacity: 0.6 }}>Neutral</div>
            </div>
          </div>
        </div>
      </div>

      {/* News Feed & Analysis */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '24px' }}>
        {/* News Feed */}
        <div className="card">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
            <h3 style={{ fontSize: '16px', fontWeight: 600 }}>News Feed</h3>
            <span style={{ fontSize: '12px', opacity: 0.5 }}>Last 24h</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            <div style={{ padding: '16px', background: 'rgba(41, 98, 255, 0.08)', border: '1px solid rgba(41, 98, 255, 0.2)', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span className="badge badge-positive">BULLISH</span>
                <span style={{ fontSize: '11px', opacity: 0.5 }}>2h ago</span>
              </div>
              <div style={{ fontWeight: 600, marginBottom: '8px' }}>EPA signals strong biodiesel mandate for 2025</div>
              <div style={{ fontSize: '12px', opacity: 0.7 }}>
                Sources indicate final RVO rule will exceed industry expectations, supporting soybean oil demand.
              </div>
              <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
                <span className="badge badge-neutral">BIOFUEL</span>
                <span className="badge badge-neutral">EPA</span>
              </div>
            </div>

            <div style={{ padding: '16px', background: 'rgba(239, 83, 80, 0.08)', border: '1px solid rgba(239, 83, 80, 0.2)', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span className="badge badge-negative">BEARISH</span>
                <span style={{ fontSize: '11px', opacity: 0.5 }}>5h ago</span>
              </div>
              <div style={{ fontWeight: 600, marginBottom: '8px' }}>Trump threatens 25% China tariffs on Day 1</div>
              <div style={{ fontSize: '12px', opacity: 0.7 }}>
                Truth Social post indicates immediate trade action. Market uncertainty rising.
              </div>
              <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
                <span className="badge badge-neutral">TRUMP EFFECT</span>
                <span className="badge badge-neutral">TARIFF</span>
              </div>
            </div>

            <div style={{ padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span className="badge badge-neutral">NEUTRAL</span>
                <span style={{ fontSize: '11px', opacity: 0.5 }}>8h ago</span>
              </div>
              <div style={{ fontWeight: 600, marginBottom: '8px' }}>Brazil soybean planting pace normal</div>
              <div style={{ fontSize: '12px', opacity: 0.7 }}>
                Conab reports 95% of expected area planted. Weather conditions favorable.
              </div>
              <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
                <span className="badge badge-neutral">SUPPLY</span>
                <span className="badge badge-neutral">BRAZIL</span>
              </div>
            </div>

            <div style={{ padding: '16px', background: 'rgba(41, 98, 255, 0.05)', border: '1px solid rgba(41, 98, 255, 0.15)', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
                <span className="badge badge-positive">BULLISH</span>
                <span style={{ fontSize: '11px', opacity: 0.5 }}>12h ago</span>
              </div>
              <div style={{ fontWeight: 600, marginBottom: '8px' }}>USDA export sales beat expectations</div>
              <div style={{ fontSize: '12px', opacity: 0.7 }}>
                Weekly soybean export sales up 23% vs 4-week average. China buying.
              </div>
              <div style={{ marginTop: '12px', display: 'flex', gap: '8px' }}>
                <span className="badge badge-neutral">CHINA</span>
                <span className="badge badge-neutral">EXPORTS</span>
              </div>
            </div>
          </div>
        </div>

        {/* Sentiment Metrics */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Social Sentiment */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Social Sentiment</h3>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '16px' }}>
              <div style={{ textAlign: 'center', padding: '20px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px' }}>
                <div style={{ fontSize: '32px', fontWeight: 700, color: '#2962FF' }}>68%</div>
                <div style={{ fontSize: '11px', opacity: 0.5, marginTop: '4px' }}>Twitter Bullish</div>
              </div>
              <div style={{ textAlign: 'center', padding: '20px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px' }}>
                <div style={{ fontSize: '32px', fontWeight: 700 }}>1.2k</div>
                <div style={{ fontSize: '11px', opacity: 0.5, marginTop: '4px' }}>Mentions (24h)</div>
              </div>
              <div style={{ textAlign: 'center', padding: '20px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px' }}>
                <div style={{ fontSize: '32px', fontWeight: 700, color: '#81c784' }}>+12%</div>
                <div style={{ fontSize: '11px', opacity: 0.5, marginTop: '4px' }}>Volume vs Avg</div>
              </div>
              <div style={{ textAlign: 'center', padding: '20px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px' }}>
                <div style={{ fontSize: '32px', fontWeight: 700 }}>0.65</div>
                <div style={{ fontSize: '11px', opacity: 0.5, marginTop: '4px' }}>Sentiment Score</div>
              </div>
            </div>
          </div>

          {/* COT Positioning */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>COT Positioning</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '12px', opacity: 0.6 }}>Managed Money Net</span>
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#2962FF' }}>+42,150</span>
                </div>
                <div style={{ height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: '65%', background: 'linear-gradient(90deg, #ef5350 0%, #787B86 50%, #2962FF 100%)', borderRadius: '4px', marginLeft: '35%' }}></div>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '4px', fontSize: '10px', opacity: 0.4 }}>
                  <span>Max Short</span>
                  <span>Max Long</span>
                </div>
              </div>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '12px', opacity: 0.6 }}>Producer Net</span>
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#ef5350' }}>-38,200</span>
                </div>
                <div style={{ height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: '40%', background: '#ef5350', borderRadius: '4px' }}></div>
                </div>
              </div>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px' }}>
                  <span style={{ fontSize: '12px', opacity: 0.6 }}>Swap Dealers</span>
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#787B86' }}>-2,450</span>
                </div>
                <div style={{ height: '8px', background: 'rgba(255,255,255,0.1)', borderRadius: '4px', overflow: 'hidden' }}>
                  <div style={{ height: '100%', width: '48%', background: '#787B86', borderRadius: '4px' }}></div>
                </div>
              </div>
            </div>
            <div style={{ marginTop: '16px', paddingTop: '16px', borderTop: '1px solid rgba(255,255,255,0.05)', fontSize: '11px', opacity: 0.5 }}>
              Source: CFTC COT Report — Dec 31, 2024
            </div>
          </div>

          {/* Sentiment History */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>7-Day Sentiment Trend</h3>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', height: '80px', paddingBottom: '8px', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                <div style={{ width: '24px', height: '40px', background: 'rgba(41, 98, 255, 0.6)', borderRadius: '4px' }}></div>
                <span style={{ fontSize: '10px', opacity: 0.5 }}>Mon</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                <div style={{ width: '24px', height: '52px', background: 'rgba(41, 98, 255, 0.7)', borderRadius: '4px' }}></div>
                <span style={{ fontSize: '10px', opacity: 0.5 }}>Tue</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                <div style={{ width: '24px', height: '48px', background: 'rgba(41, 98, 255, 0.65)', borderRadius: '4px' }}></div>
                <span style={{ fontSize: '10px', opacity: 0.5 }}>Wed</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                <div style={{ width: '24px', height: '36px', background: 'rgba(120, 123, 134, 0.5)', borderRadius: '4px' }}></div>
                <span style={{ fontSize: '10px', opacity: 0.5 }}>Thu</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                <div style={{ width: '24px', height: '44px', background: 'rgba(41, 98, 255, 0.55)', borderRadius: '4px' }}></div>
                <span style={{ fontSize: '10px', opacity: 0.5 }}>Fri</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                <div style={{ width: '24px', height: '56px', background: 'rgba(41, 98, 255, 0.75)', borderRadius: '4px' }}></div>
                <span style={{ fontSize: '10px', opacity: 0.5 }}>Sat</span>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                <div style={{ width: '24px', height: '60px', background: '#2962FF', borderRadius: '4px' }}></div>
                <span style={{ fontSize: '10px', opacity: 0.5 }}>Sun</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
