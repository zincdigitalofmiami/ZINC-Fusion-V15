import { TopNav } from "@/components/nav";

export default function LegislationPage() {
  return (
    <div className="min-h-screen bg-app-bg text-text-primary">
      <TopNav />
      <main className="mx-auto w-full max-w-6xl px-6 py-10">
        <h1 className="text-3xl font-semibold tracking-tight">Legislation</h1>
        <p className="mt-2 text-sm text-text-tertiary">
          Policy-driven demand and regulatory risk.
        </p>
        <div className="mt-8 rounded-lg border border-white/10 bg-card-bg p-6">
          <p className="text-sm text-text-secondary">No legislation data available.</p>
        </div>
      </main>
    </div>
  );
}
