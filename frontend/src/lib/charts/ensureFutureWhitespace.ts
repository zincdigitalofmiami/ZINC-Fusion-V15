/**
 * ensureFutureWhitespace.ts
 *
 * Extends candlestick series data with empty future time slots (WhitespaceData)
 * so that forecast target zones can render to the right of the last real candle.
 *
 * Lightweight Charts requires explicit time points to exist in the data before
 * timeToCoordinate() can resolve them. WhitespaceData ({time}) is the canonical
 * way to create future slots without fabricating OHLC values.
 *
 * Reference: https://tradingview.github.io/lightweight-charts/tutorials/demos/whitespace
 */
import type {
  CandlestickData,
  UTCTimestamp,
  WhitespaceData,
} from "lightweight-charts";

const DAY = 24 * 60 * 60;

function isWeekendUTC(ts: number): boolean {
  const d = new Date(ts * 1000);
  const day = d.getUTCDay(); // 0 Sun … 6 Sat
  return day === 0 || day === 6;
}

function nextBusinessDayUTC(ts: number): number {
  let t = ts + DAY;
  while (isWeekendUTC(t)) t += DAY;
  return t;
}

/**
 * Append WhitespaceData points from the last candle through maxFutureTime so
 * timeToCoordinate() works for future dates.
 *
 * Only appends business days (Mon–Fri) to match commodity futures calendars.
 * Returns a new array — the original is not mutated.
 */
export function ensureFutureWhitespace(
  candles: Array<CandlestickData<UTCTimestamp> | WhitespaceData<UTCTimestamp>>,
  maxFutureTime: UTCTimestamp,
): Array<CandlestickData<UTCTimestamp> | WhitespaceData<UTCTimestamp>> {
  if (candles.length === 0) return candles;

  const last = candles[candles.length - 1].time as number;
  if ((maxFutureTime as number) <= last) return candles;

  const out = candles.slice();
  let t = last;
  while (t < (maxFutureTime as number)) {
    t = nextBusinessDayUTC(t);
    out.push({ time: t as UTCTimestamp });
  }
  return out;
}
