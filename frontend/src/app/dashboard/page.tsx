import ZLPriceChart from '@/components/ZLPriceChart'

export default function DashboardPage() {
  return (
    <div>
      <h1 className="text-4xl font-bold mb-10 text-text-strong">Dashboard</h1>

      <div className="grid" style={{ gridTemplateColumns: 'repeat(12, 1fr)', gap: 24 }}>
        <div className="card" style={{ gridColumn: 'span 3' }}>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>Current ZL</div>
          <div style={{ fontSize: 32, fontWeight: 800, color: 'var(--text-strong)' }}>$47.82</div>
          <div style={{ fontSize: 13, marginTop: 6, color: 'var(--up)' }}>+1.24 (2.7%)</div>
        </div>

        <div className="card" style={{ gridColumn: 'span 3' }}>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>1 Week Forecast (P50)</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-strong)' }}>$48.50</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 14, fontSize: 12, color: 'var(--text-muted)' }}>
            <span>P10 $47.20</span>
            <span>P90 $49.80</span>
          </div>
        </div>

        <div className="card" style={{ gridColumn: 'span 3' }}>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>1 Month Forecast (P50)</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--text-strong)' }}>$49.20</div>
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 14, fontSize: 12, color: 'var(--text-muted)' }}>
            <span>P10 $46.80</span>
            <span>P90 $51.60</span>
          </div>
        </div>

        <div className="card" style={{ gridColumn: 'span 3' }}>
          <div style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 8 }}>Status</div>
          <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--warn)' }}>Monitoring</div>
          <div style={{ fontSize: 12, marginTop: 10, color: 'var(--text-muted)' }}>No automated actions</div>
        </div>

        <div className="card" style={{ gridColumn: 'span 12' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12 }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text-strong)' }}>ZL Price</div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Demo data (wire to API next)</div>
          </div>
          <ZLPriceChart />
        </div>
      </div>
    </div>
  );
}
