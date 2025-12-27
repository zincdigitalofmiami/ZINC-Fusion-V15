"use client";

import { useEffect, useState } from "react";

type HealthPayload = {
  status?: string;
};

type ErrorPayload = {
  detail?: string;
  hint?: string;
  current_base?: string;
};

async function readErrorDetail(response: Response): Promise<string> {
  try {
    const data = (await response.json()) as ErrorPayload;
    const parts = [data.detail, data.hint, data.current_base ? `API base: ${data.current_base}` : ""].filter(
      Boolean,
    ) as string[];
    if (parts.length) return parts.join(" ");
  } catch {
    // ignore
  }
  return `Request failed (${response.status})`;
}

export function ConnectionBanner() {
  const [status, setStatus] = useState<"ok" | "error" | "loading">("loading");
  const [message, setMessage] = useState<string>("");

  useEffect(() => {
    const run = async () => {
      try {
        const response = await fetch("/api/health", { cache: "no-store" });
        if (!response.ok) {
          setStatus("error");
          setMessage(await readErrorDetail(response));
          return;
        }
        const payload = (await response.json()) as HealthPayload;
        if (payload.status !== "ok") {
          setStatus("error");
          setMessage("Backend health check did not return ok.");
          return;
        }
        setStatus("ok");
        setMessage("");
      } catch (err) {
        setStatus("error");
        setMessage(err instanceof Error ? err.message : "Unknown error");
      }
    };
    run();
  }, []);

  if (status === "loading") return null;

  if (status === "ok") {
    return (
      <div className="mx-auto w-full max-w-6xl px-6 pt-6">
        <div className="rounded-lg border border-white/10 bg-card-bg px-4 py-3 text-sm text-text-secondary">
          Connected to backend.
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-6xl px-6 pt-6">
      <div className="rounded-lg border border-red-500/30 bg-card-bg px-4 py-3 text-sm text-text-secondary">
        <div className="font-semibold text-text-primary">Not connected to backend.</div>
        <div className="mt-1 text-text-tertiary">{message}</div>
        <div className="mt-2 text-text-tertiary">
          Set <code className="text-text-secondary">NEXT_PUBLIC_API_BASE</code> in Vercel to your deployed
          fusion-api URL.
        </div>
      </div>
    </div>
  );
}

