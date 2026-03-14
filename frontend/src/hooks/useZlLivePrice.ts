"use client";

import { useSyncExternalStore } from "react";

export interface ZlLivePrice {
  price: number;
  open: number;
  high: number;
  low: number;
  volume: number;
  timestamp: string;
  updated_at: string;
  previous_close: number | null;
  change: number | null;
  change_pct: number | null;
  source: string;
  live: boolean;
  age_seconds: number | null;
}

const POLL_INTERVAL_MS = 10_000;

let snapshot: ZlLivePrice | null = null;
let pollTimer: number | null = null;
let inflight: Promise<void> | null = null;
const listeners = new Set<() => void>();

function emit() {
  for (const listener of listeners) {
    listener();
  }
}

function normalizePayload(payload: unknown): ZlLivePrice | null {
  if (!payload || typeof payload !== "object") return null;

  const record = payload as Record<string, unknown>;
  const price = Number(record.price);
  if (!Number.isFinite(price) || price <= 0) return null;

  const open = Number(record.open ?? record.price);
  const high = Number(record.high ?? record.price);
  const low = Number(record.low ?? record.price);
  const volume = Number(record.volume ?? 0);

  return {
    price,
    open: Number.isFinite(open) ? open : price,
    high: Number.isFinite(high) ? high : price,
    low: Number.isFinite(low) ? low : price,
    volume: Number.isFinite(volume) ? volume : 0,
    timestamp:
      typeof record.timestamp === "string" ? record.timestamp : "",
    updated_at:
      typeof record.updated_at === "string" ? record.updated_at : "",
    previous_close:
      record.previous_close == null ? null : Number(record.previous_close),
    change: record.change == null ? null : Number(record.change),
    change_pct:
      record.change_pct == null ? null : Number(record.change_pct),
    source: typeof record.source === "string" ? record.source : "unknown",
    live: Boolean(record.live),
    age_seconds:
      record.age_seconds == null ? null : Number(record.age_seconds),
  };
}

async function refreshSnapshot() {
  if (typeof window === "undefined") return;
  if (inflight) return inflight;

  inflight = (async () => {
    try {
      const res = await fetch("/api/zl/live", { cache: "no-store" });
      if (!res.ok) {
        throw new Error(`ZL live fetch failed with ${res.status}`);
      }

      const nextSnapshot = normalizePayload(await res.json());
      if (JSON.stringify(snapshot) !== JSON.stringify(nextSnapshot)) {
        snapshot = nextSnapshot;
        emit();
      }
    } catch (error) {
      console.error("Failed to refresh shared ZL live price:", error);
    } finally {
      inflight = null;
    }
  })();

  return inflight;
}

function startPolling() {
  if (typeof window === "undefined" || pollTimer) return;

  void refreshSnapshot();
  pollTimer = window.setInterval(() => {
    void refreshSnapshot();
  }, POLL_INTERVAL_MS);
}

function stopPollingIfIdle() {
  if (listeners.size > 0 || !pollTimer) return;
  clearInterval(pollTimer);
  pollTimer = null;
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  startPolling();

  return () => {
    listeners.delete(listener);
    stopPollingIfIdle();
  };
}

function getSnapshot() {
  return snapshot;
}

function getServerSnapshot() {
  return null;
}

export function useZlLivePrice(): ZlLivePrice | null {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
