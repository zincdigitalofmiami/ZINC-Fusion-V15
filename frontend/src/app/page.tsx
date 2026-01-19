'use client';

import Link from 'next/link'
import { NeuralSphere } from '@/components/viz/NeuralSphere'

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
                <div className="stat-number">52</div>
                <div className="stat-label">Models</div>
              </div>
            </div>
          </div>
          <div className="hero-visual">
            <NeuralSphere
              size={800}
              color="#aaaaaa"
              particleColor="#666666"
              wireframeOpacity={0.45}
              rotationSpeed={0.0005}
            />
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
            © 2026 ZINC FUSION. Proprietary commodity intelligence system.
          </p>
        </div>
      </footer>
    </>
  )
}
