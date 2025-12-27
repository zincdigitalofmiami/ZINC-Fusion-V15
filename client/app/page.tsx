import Link from "next/link";

export default function Home() {
  return (
    <div className="min-h-screen bg-app-bg text-text-primary">
      <header className="w-full border-b border-white/5 bg-app-bg/80 backdrop-blur">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between px-6 py-5">
          <div className="flex items-center gap-3">
            <div className="h-10 w-10 rounded-lg bg-gradient-blue" />
            <div>
              <div className="text-sm font-semibold tracking-wide">ZL Intelligence</div>
              <div className="text-xs text-text-tertiary">Soybean Oil • Quant Desk</div>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/dashboard"
              className="rounded-md border border-white/10 bg-card-bg px-4 py-2 text-sm text-text-secondary hover:border-white/20 hover:text-text-primary"
            >
              View Dashboard
            </Link>
            <Link
              href="/strategy"
              className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500"
            >
              Strategy
            </Link>
          </div>
        </div>
      </header>

      <main className="mx-auto w-full max-w-6xl px-6 pb-16 pt-14">
        <section className="grid gap-10 lg:grid-cols-2 lg:items-center">
          <div>
            <h1 className="text-balance text-4xl font-semibold tracking-tight md:text-5xl">
              Commodity intelligence that stays connected to reality.
            </h1>
            <p className="mt-5 max-w-xl text-pretty text-base text-text-tertiary">
              Price, drivers, forecasts, and procurement posture — backed by your DuckDB pipeline and
              trained models. No mystery dashboards. No dead pages.
            </p>

            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Link
                href="/dashboard"
                className="rounded-md bg-primary px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
              >
                Open Dashboard
              </Link>
              <Link
                href="/sentiment"
                className="rounded-md border border-white/10 bg-card-bg px-5 py-2.5 text-sm text-text-secondary hover:border-white/20 hover:text-text-primary"
              >
                Sentiment
              </Link>
              <Link
                href="/legislation"
                className="rounded-md border border-white/10 bg-card-bg px-5 py-2.5 text-sm text-text-secondary hover:border-white/20 hover:text-text-primary"
              >
                Legislation
              </Link>
              <Link
                href="/vegas-intel"
                className="rounded-md border border-white/10 bg-card-bg px-5 py-2.5 text-sm text-text-secondary hover:border-white/20 hover:text-text-primary"
              >
                Vegas Intel
              </Link>
            </div>
          </div>

          <div className="rounded-2xl border border-white/10 bg-card-bg p-6">
            <div className="grid grid-cols-2 gap-4">
              <div className="rounded-xl border border-white/10 bg-card-elevated p-4">
                <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
                  Models
                </div>
                <div className="mt-2 text-3xl font-bold font-mono">11</div>
                <div className="mt-2 text-xs text-text-tertiary">
                  1 Core + 10 Specialists
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-card-elevated p-4">
                <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
                  Horizons
                </div>
                <div className="mt-2 text-3xl font-bold font-mono">4</div>
                <div className="mt-2 text-xs text-text-tertiary">5 / 21 / 63 / 126</div>
              </div>
              <div className="rounded-xl border border-white/10 bg-card-elevated p-4">
                <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
                  Data Layer
                </div>
                <div className="mt-2 text-sm font-semibold text-text-primary">DuckDB</div>
                <div className="mt-2 text-xs text-text-tertiary">
                  raw → features → training → forecasts
                </div>
              </div>
              <div className="rounded-xl border border-white/10 bg-card-elevated p-4">
                <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
                  Status
                </div>
                <div className="mt-2 text-sm font-semibold text-text-primary">Connected</div>
                <div className="mt-2 text-xs text-text-tertiary">
                  UI reads live from API routes
                </div>
              </div>
            </div>

            <div className="mt-6 rounded-xl border border-white/10 bg-[#0B1224] p-4">
              <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
                What to check first
              </div>
              <ul className="mt-3 space-y-2 text-sm text-text-secondary">
                <li className="flex items-center justify-between gap-3">
                  <span>Drivers → latest Big-10 scores</span>
                  <Link className="text-primary hover:underline" href="/dashboard">
                    Open
                  </Link>
                </li>
                <li className="flex items-center justify-between gap-3">
                  <span>Forecast bands → p10/p50/p90 overlays</span>
                  <Link className="text-primary hover:underline" href="/dashboard">
                    Open
                  </Link>
                </li>
                <li className="flex items-center justify-between gap-3">
                  <span>Procurement posture + risk framing</span>
                  <Link className="text-primary hover:underline" href="/strategy">
                    Open
                  </Link>
                </li>
              </ul>
            </div>
          </div>
        </section>

        <section className="mt-14 grid gap-6 md:grid-cols-3">
          <div className="rounded-xl border border-white/10 bg-card-bg p-6">
            <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
              Audit & Guard
            </div>
            <h2 className="mt-3 text-lg font-semibold">Validate data quality</h2>
            <p className="mt-2 text-sm text-text-tertiary">
              Detect missing coverage, schema drift, and broken joins before it contaminates
              training.
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-card-bg p-6">
            <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
              Forecast
            </div>
            <h2 className="mt-3 text-lg font-semibold">Generate quantile bands</h2>
            <p className="mt-2 text-sm text-text-tertiary">
              Probabilistic outputs (p10/p50/p90) across locked horizons for planning and risk.
            </p>
          </div>
          <div className="rounded-xl border border-white/10 bg-card-bg p-6">
            <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
              Analyze
            </div>
            <h2 className="mt-3 text-lg font-semibold">Explain drivers</h2>
            <p className="mt-2 text-sm text-text-tertiary">
              Track pressure from crush, China, FX, Fed, energy, and the rest — as scorecards.
            </p>
          </div>
        </section>
      </main>
    </div>
  );
}
