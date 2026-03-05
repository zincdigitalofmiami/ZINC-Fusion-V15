'use client';

import React, { useEffect, useMemo, useState } from 'react';
import { CloudRain } from 'lucide-react';

interface WeatherRegion {
  region: string;
  stations: number;
  avgPrecipMm: number | null;
  avgTempC: number | null;
}

interface WeatherStation {
  stationId: string;
  region: string;
  precipMm: number | null;
  snowMm: number | null;
  tempC: number | null;
}

interface WeatherRiskResponse {
  asOfDate: string | null;
  stationCount: number;
  regions: WeatherRegion[];
  stations: WeatherStation[];
}

function cellClass(station: WeatherStation): string {
  const snow = station.snowMm ?? 0;
  const precip = station.precipMm ?? 0;

  if (snow >= 1) return 'bg-slate-200/20 border-slate-200/40';
  if (precip >= 8) return 'bg-blue-500/35 border-blue-400/60';
  if (precip >= 3) return 'bg-blue-500/20 border-blue-500/40';
  if (precip <= 0.5) return 'bg-amber-500/10 border-amber-500/30';
  return 'bg-emerald-500/10 border-emerald-500/30';
}

export function WeatherRiskArray() {
  const [data, setData] = useState<WeatherRiskResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function loadWeather() {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch('/api/weather-risk', { cache: 'no-store' });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as WeatherRiskResponse;
        if (!cancelled) setData(json);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : 'Failed to load weather');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    loadWeather();
    return () => {
      cancelled = true;
    };
  }, []);

  const stations = useMemo(
    () => (data?.stations ?? []).slice(0, 60),
    [data?.stations],
  );
  const wetShare = useMemo(() => {
    if (stations.length === 0) return null;
    const wet = stations.filter((s) => (s.precipMm ?? 0) >= 3 || (s.snowMm ?? 0) >= 1).length;
    return Math.round((wet / stations.length) * 100);
  }, [stations]);

  return (
    <div className="bg-[#0a0a0a] border border-white/5 rounded-xl p-6 relative overflow-hidden group">
      <div className="flex items-center justify-between mb-4 relative z-10">
        <div>
          <h3 className="text-sm font-semibold text-white uppercase tracking-wider flex items-center gap-2">
            <CloudRain size={16} className="text-blue-400" />
            NOAA Precip Matrix
          </h3>
          <p className="text-[10px] text-slate-500 font-mono mt-1">
            {loading
              ? 'Loading weather observations...'
              : data?.asOfDate
                ? `${data.stationCount} stations // as of ${data.asOfDate}`
                : 'No weather observations available'}
          </p>
        </div>
        {!loading && wetShare !== null && (
          <div className="text-right">
            <div className="text-[10px] text-slate-500 font-mono">WET STATIONS</div>
            <div className="text-sm font-bold text-cyan-300">{wetShare}%</div>
          </div>
        )}
      </div>

      {loading && (
        <div className="text-sm text-slate-400">Fetching latest NOAA station data...</div>
      )}

      {!loading && error && (
        <div className="text-sm text-red-400">Failed to load weather matrix: {error}</div>
      )}

      {!loading && !error && stations.length === 0 && (
        <div className="text-sm text-slate-400">
          Weather matrix is empty. Ingestion must populate `alt.weather_1d` first.
        </div>
      )}

      {!loading && !error && stations.length > 0 && (
        <>
          <div className="grid grid-cols-10 gap-1 mb-4">
            {stations.map((station) => (
              <div
                key={`${station.stationId}-${station.region}`}
                className={`h-6 rounded-sm border transition-all ${cellClass(station)}`}
                title={`${station.stationId} | ${station.region} | precip ${station.precipMm ?? 0} mm | snow ${station.snowMm ?? 0} mm | temp ${
                  station.tempC !== null ? `${station.tempC.toFixed(1)}C` : 'n/a'
                }`}
              />
            ))}
          </div>

          <div className="space-y-2 border-t border-white/5 pt-3">
            {(data?.regions ?? []).slice(0, 4).map((r) => (
              <div key={r.region} className="flex items-center justify-between text-[11px]">
                <span className="text-slate-400">{r.region}</span>
                <span className="text-slate-500 font-mono">
                  {r.stations} stn | {r.avgPrecipMm !== null ? `${r.avgPrecipMm.toFixed(1)} mm` : '--'} |{' '}
                  {r.avgTempC !== null ? `${r.avgTempC.toFixed(1)}C` : '--'}
                </span>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
