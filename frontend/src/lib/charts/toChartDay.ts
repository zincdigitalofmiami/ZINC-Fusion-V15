export function toChartDay(value: string | Date): string {
  if (value instanceof Date) {
    return value.toISOString().slice(0, 10);
  }

  const raw = String(value).trim();
  const match = raw.match(/^(\d{4}-\d{2}-\d{2})/);
  if (match) {
    return match[1];
  }

  const dt = new Date(raw);
  if (Number.isNaN(dt.getTime())) {
    return raw;
  }

  return dt.toISOString().slice(0, 10);
}
