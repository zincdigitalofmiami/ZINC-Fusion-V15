import type { Time } from "lightweight-charts";

export type PivotTimeframe = "D" | "W" | "M" | "Y";

export interface PivotLevels {
  pp: number;
  r1: number;
  s1: number;
  r2: number;
  s2: number;
  r3: number;
  s3: number;
  r4: number;
  s4: number;
  r5: number;
  s5: number;
}

export interface PivotLine {
  timeframe: PivotTimeframe;
  level: string;
  label: string;
  price: number;
  startTime?: Time;
}

interface PivotSourceBar {
  timestamp: string;
  high: number;
  low: number;
  close: number;
}

interface PeriodAggregate {
  key: string;
  startTime: string;
  high: number;
  low: number;
  close: number;
}

const LEVEL_KEYS: Array<{ key: keyof PivotLevels; label: string }> = [
  { key: "pp", label: "P" },
  { key: "r1", label: "R1" },
  { key: "s1", label: "S1" },
  { key: "r2", label: "R2" },
  { key: "s2", label: "S2" },
  { key: "r3", label: "R3" },
  { key: "s3", label: "S3" },
  { key: "r4", label: "R4" },
  { key: "s4", label: "S4" },
  { key: "r5", label: "R5" },
  { key: "s5", label: "S5" },
];

export function calculateTraditionalPivots(
  high: number,
  low: number,
  close: number,
): PivotLevels {
  const pp = (high + low + close) / 3;
  const range = high - low;

  return {
    pp,
    r1: pp * 2 - low,
    s1: pp * 2 - high,
    r2: pp + range,
    s2: pp - range,
    r3: pp * 2 + (high - 2 * low),
    s3: pp * 2 - (2 * high - low),
    r4: pp * 3 + (high - 3 * low),
    s4: pp * 3 - (3 * high - low),
    r5: pp * 4 + (high - 4 * low),
    s5: pp * 4 - (4 * high - low),
  };
}

export function pivotLevelsToLines(
  levels: PivotLevels,
  timeframe: PivotTimeframe,
  maxLevel = 5,
): PivotLine[] {
  return LEVEL_KEYS.filter(({ label }) => {
    if (label === "P") return true;
    const numericLevel = parseInt(label.slice(1), 10);
    return numericLevel <= maxLevel;
  }).map(({ key, label }) => ({
    timeframe,
    level: label,
    label: `${timeframe}(${label})`,
    price: levels[key],
  }));
}

function toDateKey(value: string): string {
  const match = String(value).match(/^(\d{4}-\d{2}-\d{2})/);
  if (match) return match[1];

  const dt = new Date(value);
  if (Number.isNaN(dt.getTime())) return value;
  return dt.toISOString().slice(0, 10);
}

function parseDateKey(value: string): Date {
  return new Date(`${toDateKey(value)}T00:00:00Z`);
}

function toKey(value: Date): string {
  return value.toISOString().slice(0, 10);
}

function weekStartKey(value: string): string {
  const dt = parseDateKey(value);
  const day = dt.getUTCDay() || 7;
  dt.setUTCDate(dt.getUTCDate() - day + 1);
  return toKey(dt);
}

function monthStartKey(value: string): string {
  const dt = parseDateKey(value);
  dt.setUTCDate(1);
  return toKey(dt);
}

function yearStartKey(value: string): string {
  const dt = parseDateKey(value);
  dt.setUTCMonth(0, 1);
  return toKey(dt);
}

function aggregatePeriods(
  bars: PivotSourceBar[],
  keyForBar: (timestamp: string) => string,
): PeriodAggregate[] {
  const periods: PeriodAggregate[] = [];

  for (const bar of bars) {
    const key = keyForBar(bar.timestamp);
    const previous = periods[periods.length - 1];

    if (!previous || previous.key !== key) {
      periods.push({
        key,
        startTime: toDateKey(bar.timestamp),
        high: bar.high,
        low: bar.low,
        close: bar.close,
      });
      continue;
    }

    previous.high = Math.max(previous.high, bar.high);
    previous.low = Math.min(previous.low, bar.low);
    previous.close = bar.close;
  }

  return periods;
}

function buildPeriodPivotLines(
  periods: PeriodAggregate[],
  timeframe: PivotTimeframe,
  maxLevel: number,
): PivotLine[] {
  if (periods.length < 2) return [];

  const source = periods[periods.length - 2];
  const current = periods[periods.length - 1];

  return pivotLevelsToLines(
    calculateTraditionalPivots(source.high, source.low, source.close),
    timeframe,
    maxLevel,
  ).map((line) => ({
    ...line,
    startTime: current.startTime,
  }));
}

export function buildPivotLines(
  bars: PivotSourceBar[],
): PivotLine[] {
  if (bars.length < 2) return [];

  const sortedBars = [...bars].sort((a, b) =>
    toDateKey(a.timestamp).localeCompare(toDateKey(b.timestamp)),
  );
  const currentBar = sortedBars[sortedBars.length - 1];
  const previousDayBar = sortedBars[sortedBars.length - 2];

  const daily = pivotLevelsToLines(
    calculateTraditionalPivots(
      previousDayBar.high,
      previousDayBar.low,
      previousDayBar.close,
    ),
    "D",
    3,
  ).map((line) => ({
    ...line,
    startTime: toDateKey(currentBar.timestamp),
  }));

  const weekly = buildPeriodPivotLines(
    aggregatePeriods(sortedBars, (timestamp) => weekStartKey(timestamp)),
    "W",
    2,
  );
  const monthly = buildPeriodPivotLines(
    aggregatePeriods(sortedBars, (timestamp) => monthStartKey(timestamp)),
    "M",
    2,
  );
  const yearly = buildPeriodPivotLines(
    aggregatePeriods(sortedBars, (timestamp) => yearStartKey(timestamp)),
    "Y",
    1,
  );

  return [...daily, ...weekly, ...monthly, ...yearly];
}
