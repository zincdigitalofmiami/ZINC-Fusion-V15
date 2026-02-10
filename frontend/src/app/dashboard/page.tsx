'use client';

import React, { useEffect, useState } from 'react';
import { LightweightZlCandlestickChart } from '@/components/LightweightZlCandlestickChart';
import { ChrisTop4Drivers } from '@/components/ChrisTop4Drivers';
import { SignalGauge } from '@/components/ui/SignalGauge';

interface ForecastPoint {
  horizon_days: number;
  as_of_date: string;
  forecast_date: string;
  price_p30: number | null;
  price_p50: number | null;
  price_p70: number | null;
  current_price: number | null;
}

interface ForecastData {
  symbol: string;
  as_of_date: string | null;
  current_price: number | null;
  horizons: number[];
  forecasts: ForecastPoint[];
}

export default function DashboardPage() {
  const [forecastData, setForecastData] = useState<ForecastData | null>(null);
  const [forecastLoading, setForecastLoading] = useState(true);
  const [forecastError, setForecastError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchForecasts() {
      try {
        const res = await fetch('/api/zl/forecast');
        if (res.status === 404) {
          // Model not run yet — no forecast data exists
          setForecastData(null);
          setForecastError(null);
        } else if (!res.ok) {
          throw new Error(`HTTP ${res.status}`);
        } else {
          const data = await res.json();
          setForecastData(data);
          setForecastError(null);
        }
      } catch (err) {
        console.error('Failed to fetch forecasts:', err);
        setForecastError(err instanceof Error ? err.message : 'Failed to load');
      } finally {
        setForecastLoading(false);
      }
    }
    fetchForecasts();
    // Refresh every 5 minutes
    const interval = setInterval(fetchForecasts, 300000);
    return () => clearInterval(interval);
  }, []);

  // Map horizon days to labels
  const getHorizonLabel = (days: number): string => {
    const labels: Record<number, string> = {
      5: '1 Week',
      21: '1 Month',
      63: '3 Months',
      126: '6 Months'
    };
    return labels[days] || `${days}d`;
  };

  // Calculate signal value (0-100) from forecast direction
  const calculateSignalValue = (forecast: ForecastPoint): number => {
    if (!forecast.price_p50 || !forecast.current_price) return 50;

    const changePct = ((forecast.price_p50 - forecast.current_price) / forecast.current_price) * 100;

    // Map percentage change to 0-100 scale
    // >5% = 80-100 (strong buy)
    // 2-5% = 60-80 (buy)
    // -2 to 2% = 40-60 (neutral)
    // -5 to -2% = 20-40 (sell)
    // <-5% = 0-20 (strong sell)

    if (changePct >= 5) return 80 + Math.min(20, (changePct - 5) * 4);
    if (changePct >= 2) return 60 + (changePct - 2) * 6.67;
    if (changePct >= -2) return 40 + (changePct * 10);
    if (changePct >= -5) return 20 + ((changePct + 5) * 6.67);
    return Math.max(0, 20 + (changePct + 5) * 4);
  };

  // Calculate confidence based on spread width
  const calculateConfidence = (forecast: ForecastPoint): string => {
    if (!forecast.price_p30 || !forecast.price_p70 || !forecast.current_price) return 'Low';

    const spread = forecast.price_p70 - forecast.price_p30;
    const spreadPct = (spread / forecast.current_price) * 100;

    // Tighter spread = higher confidence
    if (spreadPct < 8) return 'High';
    if (spreadPct < 15) return 'Med';
    return 'Low';
  };

  const fcPoints = forecastData?.forecasts ?? [];

  return (
    <div className="min-h-screen bg-[#0a0a0a] text-slate-200 px-4 pt-20 pb-8 space-y-6">

      {/* SECTION 1: HERO CHART */}
      <div>
        <LightweightZlCandlestickChart height="80vh" />
      </div>

      {/* SECTION 2: Multi-Horizon Signals - 4 Big Cards */}
      <div className="space-y-3">
        <div className="flex items-center gap-2 pl-1 border-l-4 border-blue-500">
          <h3 className="text-sm font-bold text-white uppercase tracking-wider">
            Forecast Horizons
          </h3>
          <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            4 HORIZONS
          </span>
          {forecastLoading && (
            <span className="text-[9px] text-slate-500 animate-pulse">Loading forecasts...</span>
          )}
          {!forecastLoading && forecastError && (
            <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-red-500/10 text-red-400 border border-red-500/20">
              FORECAST ERROR
            </span>
          )}
          {!forecastLoading && !forecastError && (!forecastData || fcPoints.length === 0) && (
            <span className="px-2 py-0.5 rounded text-[9px] font-bold bg-yellow-500/10 text-yellow-400 border border-yellow-500/20">
              MODEL NOT RUN
            </span>
          )}
        </div>
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {forecastLoading ? (
            // Loading skeleton
            <>
              {[1, 2, 3, 4].map((i) => (
                <div key={i} className="bg-[#0a0a0a] border border-white/5 rounded-xl p-5 animate-pulse">
                  <div className="h-6 bg-slate-700 rounded w-24 mb-4" />
                  <div className="h-24 bg-slate-700 rounded mb-4" />
                  <div className="h-8 bg-slate-700 rounded" />
                </div>
              ))}
            </>
          ) : forecastError ? (
            // API error — don't show fake neutral gauges
            <div className="col-span-full bg-red-500/5 border border-red-500/20 rounded-xl p-6 text-center">
              <p className="text-red-400 font-bold text-sm">Forecast Data Unavailable</p>
              <p className="text-slate-500 text-xs mt-1">API returned an error. Check /api/zl/forecast.</p>
            </div>
          ) : forecastData && fcPoints.length > 0 ? (
            // Real forecast data
            fcPoints.map((forecast) => (
              <SignalGauge
                key={forecast.horizon_days}
                horizon={getHorizonLabel(forecast.horizon_days)}
                value={calculateSignalValue(forecast)}
                p10={forecast.price_p30 ?? undefined}
                p90={forecast.price_p70 ?? undefined}
                confidence={calculateConfidence(forecast)}
              />
            ))
          ) : (
            // Model not run — no data exists yet
            <div className="col-span-full bg-yellow-500/5 border border-yellow-500/20 rounded-xl p-6 text-center">
              <p className="text-yellow-400 font-bold text-sm">No Forecast Data</p>
              <p className="text-slate-500 text-xs mt-1">Core model has not produced forecasts yet.</p>
            </div>
          )}
        </div>
      </div>

      {/* SECTION 3: Chris's TOP 4 Key Drivers */}
      <ChrisTop4Drivers />
    </div>
  );
}
