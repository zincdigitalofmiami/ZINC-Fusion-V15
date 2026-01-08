export default function VegasIntelPage() {
  return (
    <div className="main-content">
      <div className="page-header">
        <h1 className="page-title">Vegas Intel</h1>
        <p className="page-subtitle">Sales command center — leads, events, and opportunities</p>
      </div>

      {/* Quick Stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '24px', marginBottom: '40px' }}>
        <div className="card" style={{ textAlign: 'center', padding: '24px' }}>
          <div style={{ fontSize: '40px', fontWeight: 700, color: '#2962FF' }}>12</div>
          <div style={{ fontSize: '12px', opacity: 0.6, marginTop: '8px' }}>Active Leads</div>
        </div>
        <div className="card" style={{ textAlign: 'center', padding: '24px' }}>
          <div style={{ fontSize: '40px', fontWeight: 700, color: '#81c784' }}>$2.4M</div>
          <div style={{ fontSize: '12px', opacity: 0.6, marginTop: '8px' }}>Pipeline Value</div>
        </div>
        <div className="card" style={{ textAlign: 'center', padding: '24px' }}>
          <div style={{ fontSize: '40px', fontWeight: 700 }}>3</div>
          <div style={{ fontSize: '12px', opacity: 0.6, marginTop: '8px' }}>Upcoming Events</div>
        </div>
        <div className="card" style={{ textAlign: 'center', padding: '24px' }}>
          <div style={{ fontSize: '40px', fontWeight: 700, color: '#ffb464' }}>5</div>
          <div style={{ fontSize: '12px', opacity: 0.6, marginTop: '8px' }}>Hot Opportunities</div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '24px' }}>
        {/* Main Content */}
        <div>
          {/* Hot Leads */}
          <div className="card" style={{ marginBottom: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '24px' }}>
              <h3 style={{ fontSize: '16px', fontWeight: 600 }}>Hot Leads</h3>
              <span style={{ fontSize: '12px', padding: '4px 12px', background: 'rgba(239, 83, 80, 0.2)', borderRadius: '4px', color: '#ef5350', fontWeight: 600 }}>5 URGENT</span>
            </div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
              {/* Lead 1 */}
              <div style={{ display: 'flex', gap: '16px', padding: '20px', background: 'rgba(41, 98, 255, 0.08)', border: '1px solid rgba(41, 98, 255, 0.3)', borderRadius: '12px' }}>
                <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(41, 98, 255, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '18px' }}>
                  AC
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <span style={{ fontWeight: 600, fontSize: '15px' }}>Acme Foods Corp</span>
                    <span className="badge badge-positive">HOT</span>
                  </div>
                  <div style={{ fontSize: '13px', opacity: 0.7, marginBottom: '8px' }}>
                    Looking for 500K gallons soybean oil supply contract. Q1 delivery.
                  </div>
                  <div style={{ display: 'flex', gap: '16px', fontSize: '12px' }}>
                    <span style={{ opacity: 0.5 }}>Contact: John Smith</span>
                    <span style={{ opacity: 0.5 }}>Est. Value: $850K</span>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '11px', opacity: 0.5 }}>Next Action</div>
                  <div style={{ fontWeight: 600, color: '#2962FF' }}>Call Today</div>
                </div>
              </div>

              {/* Lead 2 */}
              <div style={{ display: 'flex', gap: '16px', padding: '20px', background: 'rgba(255, 180, 100, 0.08)', border: '1px solid rgba(255, 180, 100, 0.3)', borderRadius: '12px' }}>
                <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(255, 180, 100, 0.2)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '18px' }}>
                  MB
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <span style={{ fontWeight: 600, fontSize: '15px' }}>Midwest Biofuels LLC</span>
                    <span className="badge badge-warning">WARM</span>
                  </div>
                  <div style={{ fontSize: '13px', opacity: 0.7, marginBottom: '8px' }}>
                    Biodiesel feedstock supplier evaluation. Annual contract opportunity.
                  </div>
                  <div style={{ display: 'flex', gap: '16px', fontSize: '12px' }}>
                    <span style={{ opacity: 0.5 }}>Contact: Sarah Johnson</span>
                    <span style={{ opacity: 0.5 }}>Est. Value: $1.2M</span>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '11px', opacity: 0.5 }}>Next Action</div>
                  <div style={{ fontWeight: 600, color: '#ffb464' }}>Send Proposal</div>
                </div>
              </div>

              {/* Lead 3 */}
              <div style={{ display: 'flex', gap: '16px', padding: '20px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '12px' }}>
                <div style={{ width: '48px', height: '48px', borderRadius: '12px', background: 'rgba(255, 255, 255, 0.1)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '18px' }}>
                  GF
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                    <span style={{ fontWeight: 600, fontSize: '15px' }}>Global Fry Inc</span>
                    <span className="badge badge-neutral">NEW</span>
                  </div>
                  <div style={{ fontSize: '13px', opacity: 0.7, marginBottom: '8px' }}>
                    Restaurant chain seeking cooking oil supplier. 50 locations.
                  </div>
                  <div style={{ display: 'flex', gap: '16px', fontSize: '12px' }}>
                    <span style={{ opacity: 0.5 }}>Contact: Mike Chen</span>
                    <span style={{ opacity: 0.5 }}>Est. Value: $320K</span>
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '11px', opacity: 0.5 }}>Next Action</div>
                  <div style={{ fontWeight: 600 }}>Qualify Lead</div>
                </div>
              </div>
            </div>
          </div>

          {/* Upcoming Events */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '24px' }}>Upcoming Events & Meetings</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', background: 'rgba(41, 98, 255, 0.05)', border: '1px solid rgba(41, 98, 255, 0.2)', borderRadius: '8px' }}>
                <div style={{ textAlign: 'center', minWidth: '50px' }}>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>8</div>
                  <div style={{ fontSize: '10px', opacity: 0.6 }}>JAN</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>Acme Foods — Contract Review</div>
                  <div style={{ fontSize: '12px', opacity: 0.6 }}>10:00 AM — Video Call</div>
                </div>
                <div style={{ padding: '4px 12px', background: 'rgba(41, 98, 255, 0.2)', borderRadius: '4px', fontSize: '11px', fontWeight: 600, color: '#2962FF' }}>TODAY</div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px' }}>
                <div style={{ textAlign: 'center', minWidth: '50px' }}>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>12</div>
                  <div style={{ fontSize: '10px', opacity: 0.6 }}>JAN</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>Midwest Biofuels — Plant Tour</div>
                  <div style={{ fontSize: '12px', opacity: 0.6 }}>2:00 PM — On-site</div>
                </div>
                <div style={{ padding: '4px 12px', background: 'rgba(255, 255, 255, 0.1)', borderRadius: '4px', fontSize: '11px', fontWeight: 600, opacity: 0.6 }}>4 DAYS</div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '16px', background: 'rgba(255, 255, 255, 0.02)', border: '1px solid rgba(255, 255, 255, 0.1)', borderRadius: '8px' }}>
                <div style={{ textAlign: 'center', minWidth: '50px' }}>
                  <div style={{ fontSize: '20px', fontWeight: 700 }}>15</div>
                  <div style={{ fontSize: '10px', opacity: 0.6 }}>JAN</div>
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>NOPA Conference — Las Vegas</div>
                  <div style={{ fontSize: '12px', opacity: 0.6 }}>All Day — Venetian Hotel</div>
                </div>
                <div style={{ padding: '4px 12px', background: 'rgba(255, 180, 100, 0.2)', borderRadius: '4px', fontSize: '11px', fontWeight: 600, color: '#ffb464' }}>7 DAYS</div>
              </div>
            </div>
          </div>
        </div>

        {/* Sidebar */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          {/* Market Talking Points */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Market Talking Points</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ padding: '12px', background: 'rgba(41, 98, 255, 0.1)', borderRadius: '8px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: '#2962FF', marginBottom: '8px' }}>BULLISH POINT</div>
                <div style={{ fontSize: '13px', lineHeight: 1.5 }}>
                  &ldquo;EPA RVO rule expected to boost biodiesel demand 15%. Lock in supply now before Q1 price surge.&rdquo;
                </div>
              </div>
              <div style={{ padding: '12px', background: 'rgba(255, 180, 100, 0.1)', borderRadius: '8px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, color: '#ffb464', marginBottom: '8px' }}>URGENCY DRIVER</div>
                <div style={{ fontSize: '13px', lineHeight: 1.5 }}>
                  &ldquo;Trump tariff threats creating uncertainty. Secure contracts before potential trade disruption.&rdquo;
                </div>
              </div>
              <div style={{ padding: '12px', background: 'rgba(255, 255, 255, 0.05)', borderRadius: '8px' }}>
                <div style={{ fontSize: '12px', fontWeight: 600, marginBottom: '8px' }}>VALUE PROP</div>
                <div style={{ fontSize: '13px', lineHeight: 1.5 }}>
                  &ldquo;Our AI forecasts show 87% confidence in near-term price support. Ideal timing for annual contracts.&rdquo;
                </div>
              </div>
            </div>
          </div>

          {/* Competitor Intel */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Competitor Intel</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px' }}>
                <div>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>Bunge</div>
                  <div style={{ fontSize: '11px', opacity: 0.5 }}>Aggressive Q1 pricing</div>
                </div>
                <span className="badge badge-negative">THREAT</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px' }}>
                <div>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>ADM</div>
                  <div style={{ fontSize: '11px', opacity: 0.5 }}>Capacity constraints</div>
                </div>
                <span className="badge badge-positive">OPPORTUNITY</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '12px', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px' }}>
                <div>
                  <div style={{ fontWeight: 600, marginBottom: '4px' }}>Cargill</div>
                  <div style={{ fontSize: '11px', opacity: 0.5 }}>Focus on biofuel sector</div>
                </div>
                <span className="badge badge-neutral">NEUTRAL</span>
              </div>
            </div>
          </div>

          {/* Quick Actions */}
          <div className="card">
            <h3 style={{ fontSize: '16px', fontWeight: 600, marginBottom: '20px' }}>Quick Actions</h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              <button style={{ width: '100%', padding: '12px', background: '#2962FF', border: 'none', borderRadius: '8px', color: 'white', fontWeight: 600, cursor: 'pointer' }}>
                + Add New Lead
              </button>
              <button style={{ width: '100%', padding: '12px', background: 'rgba(255, 255, 255, 0.1)', border: '1px solid rgba(255, 255, 255, 0.2)', borderRadius: '8px', color: 'white', fontWeight: 600, cursor: 'pointer' }}>
                Schedule Meeting
              </button>
              <button style={{ width: '100%', padding: '12px', background: 'rgba(255, 255, 255, 0.1)', border: '1px solid rgba(255, 255, 255, 0.2)', borderRadius: '8px', color: 'white', fontWeight: 600, cursor: 'pointer' }}>
                Export Report
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
