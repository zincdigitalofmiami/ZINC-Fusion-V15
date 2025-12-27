import { TopNav } from "@/components/nav";

export default function VegasIntelPage() {
  return (
    <div className="min-h-screen bg-app-bg text-text-primary">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-10">
        <h1 className="text-3xl font-semibold tracking-tight">Vegas Intel</h1>
        <p className="mt-2 text-sm text-text-tertiary">
          Physical, local demand intelligence.
        </p>
        <div className="mt-8 rounded-lg border border-white/10 bg-card-bg p-6">
          <p className="text-sm text-text-secondary">No Vegas Intel data available.</p>
        </div>
      </main>
    </div>
  );
}
