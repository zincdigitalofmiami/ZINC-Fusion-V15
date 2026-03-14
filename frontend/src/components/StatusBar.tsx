"use client";

import { useEffect, useState } from "react";
import { useZlLivePrice } from "@/hooks/useZlLivePrice";

interface StatusBarProps {
  regime?: "stable" | "rising" | "falling" | "volatile" | "crisis";
  confidence?: number;
}

export default function StatusBar({ regime, confidence }: StatusBarProps) {
  const [displayTime, setDisplayTime] = useState<string>("");
  const zlData = useZlLivePrice();

  useEffect(() => {
    const formatTime = () => {
      const now = new Date();
      return now.toLocaleTimeString("en-US", {
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
        hour12: false,
      });
    };
    setDisplayTime(formatTime());
    const interval = setInterval(() => setDisplayTime(formatTime()), 1000);
    return () => clearInterval(interval);
  }, []);

  const zlPrice = zlData?.price ?? null;
  const zlChange = zlData?.change ?? null;
  const zlChangePercent = zlData?.change_pct ?? null;
  const isPositive = (zlChange ?? 0) >= 0;
  const priceChangeClass = isPositive ? "positive" : "negative";

  const regimeLabels: Record<string, string> = {
    stable: "Stable",
    rising: "Rising",
    falling: "Falling",
    volatile: "Volatile",
    crisis: "Crisis",
  };

  const confidenceClass = (confidence ?? 0) >= 80 ? "high" : "";

  return (
    <div className="status-bar">
      <div className="status-left">
        <div className="zl-price">
          ZL: {zlPrice != null ? `$${zlPrice.toFixed(2)}` : "--"}
          {zlChange != null && zlChangePercent != null && (
            <span className={`price-delta ${priceChangeClass}`}>
              {" "}
              {isPositive ? "+" : ""}
              {zlChange.toFixed(2)} ({isPositive ? "+" : ""}
              {zlChangePercent.toFixed(2)}%)
            </span>
          )}
          {zlData?.live && (
            <span className="live-dot" title="Live 1m data">
              ●
            </span>
          )}
          {zlData && !zlData.live && (
            <span className="stale-dot" title={`Last update: ${zlData.source}`}>
              ○
            </span>
          )}
        </div>
        {regime && (
          <div className={`regime-chip ${regime}`}>{regimeLabels[regime]}</div>
        )}
        {confidence != null && (
          <div className={`confidence-badge ${confidenceClass}`}>
            {confidence}% Conf
          </div>
        )}
      </div>
      <div className="status-right">
        <div className="last-update">{displayTime}</div>
        <div className="fast-actions">
          <button className="action-btn">↻</button>
          <button className="action-btn">⚙</button>
        </div>
      </div>
    </div>
  );
}
