import { HeroChart } from "@/components/hero-chart";
import { DriverCards } from "@/components/driver-cards";
import { TopNav } from "@/components/nav";
import { PulseStrip } from "@/components/pulse-strip";
import { ConnectionBanner } from "@/components/connection-banner";

export default function DashboardPage() {
  return (
    <div className="min-h-screen bg-app-bg text-text-primary">
      <TopNav />
      <main className="w-full">
        <ConnectionBanner />
        <PulseStrip />
        <HeroChart />
        <DriverCards />
      </main>
    </div>
  );
}
