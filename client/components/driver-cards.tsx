"use client";

import { useEffect, useMemo, useState } from "react";

type DriverRow = {
  as_of_date: string;
  symbol: string;
  driver_id: string;
  description?: string | null;
  score: number;
};

type Payload = {
  symbol: string;
  as_of_date: string | null;
  drivers: DriverRow[];
};

const DRIVER_ORDER = [
  "crush",
  "china",
  "fx",
  "fed",
  "tariff",
  "energy",
  "biofuel",
  "palm",
  "volatility",
  "substitutes",
] as const;

function titleCase(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function DriverCards() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const run = async () => {
      try {
        const response = await fetch(`/api/drivers/latest?symbol=ZL`, { cache: "no-store" });
        if (!response.ok) {
          const detail = await response.json().catch(() => ({}));
          setError(detail?.detail || `drivers/latest failed (${response.status})`);
          return;
        }
        const data = (await response.json()) as Payload;
        setPayload(data);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
      }
    };

    run();
  }, []);

  const drivers = useMemo(() => {
    const list = payload?.drivers || [];
    const byId = new Map(list.map((row) => [row.driver_id, row]));
    return DRIVER_ORDER.map((driverId) => byId.get(driverId)).filter(Boolean) as DriverRow[];
  }, [payload]);

  return (
    <section className="mx-auto w-full max-w-6xl px-6 pb-16">
      <div className="mt-10 flex items-end justify-between">
        <div>
          <h2 className="text-xl font-semibold text-text-primary">Drivers</h2>
          <p className="mt-1 text-sm text-text-tertiary">
            Latest Big-10 driver scores for ZL{payload?.as_of_date ? ` (as of ${payload.as_of_date})` : ""}.
          </p>
        </div>
      </div>

      {error ? (
        <div className="mt-6 rounded-lg border border-white/10 bg-card-bg p-6">
          <p className="text-sm text-text-secondary">{error}</p>
        </div>
      ) : null}

      {!error && drivers.length === 0 ? (
        <div className="mt-6 rounded-lg border border-white/10 bg-card-bg p-6">
          <p className="text-sm text-text-secondary">No driver data available.</p>
        </div>
      ) : null}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-2">
        {drivers.map((driver) => (
          <div
            key={driver.driver_id}
            className="rounded-lg border border-white/10 bg-card-bg p-6 transition-colors duration-200 hover:border-white/20"
          >
            <div className="flex items-start justify-between gap-6">
              <div>
                <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
                  {titleCase(driver.driver_id)}
                </div>
                <div className="mt-2 text-sm text-text-secondary">
                  {driver.description || ""}
                </div>
              </div>
              <div className="text-right">
                <div className="text-xs font-medium uppercase tracking-wide text-text-tertiary">
                  Score
                </div>
                <div className="mt-2 text-3xl font-bold font-mono text-text-primary">
                  {Number.isFinite(driver.score) ? driver.score.toFixed(2) : ""}
                </div>
              </div>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
