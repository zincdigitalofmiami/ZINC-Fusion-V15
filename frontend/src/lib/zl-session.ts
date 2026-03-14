/**
 * ZL (CBOT soybean oil) trades on a futures session, not a civil day.
 *
 * Session rules used here:
 * - Sunday 19:00 CT opens Monday's trade date.
 * - Monday-Thursday 19:00 CT opens the next business day's trade date.
 * - The session closes at 13:20 CT on the trade date.
 * - Friday after 13:20 CT through Sunday 18:59 CT remains the Friday session.
 *
 * The 07:45-08:30 CT pause does not change the trade date, so the rollup keeps
 * the entire overnight/day session on one session date.
 */
function pad2(value: number): string {
  return value.toString().padStart(2, "0");
}

function addDays(date: Date, days: number): Date {
  const next = new Date(date);
  next.setDate(next.getDate() + days);
  return next;
}

function previousBusinessDay(date: Date): Date {
  const prev = addDays(date, -1);
  const day = prev.getDay();
  if (day === 0) return addDays(prev, -2);
  if (day === 6) return addDays(prev, -1);
  return prev;
}

export function getZlTradeDate(now = new Date()): Date {
  const local = new Date(
    now.toLocaleString("en-US", { timeZone: "America/Chicago" }),
  );
  const day = local.getDay(); // 0=Sun, 6=Sat
  const minutes = local.getHours() * 60 + local.getMinutes();
  const openMinutes = 19 * 60;

  if (day === 6) {
    return previousBusinessDay(local);
  }

  if (day === 0) {
    return minutes >= openMinutes ? addDays(local, 1) : previousBusinessDay(local);
  }

  if (day >= 1 && day <= 4 && minutes >= openMinutes) {
    return addDays(local, 1);
  }

  return local;
}

export function getZlTradeDateString(now = new Date()): string {
  const tradeDate = getZlTradeDate(now);
  return `${tradeDate.getFullYear()}-${pad2(tradeDate.getMonth() + 1)}-${pad2(tradeDate.getDate())}`;
}

export function zlSessionContextCte(nowExpression = "NOW()"): string {
  return `
    session_clock AS (
      SELECT (${nowExpression} AT TIME ZONE 'America/Chicago') AS local_now
    ),
    session_context AS (
      SELECT
        local_now,
        CASE
          WHEN EXTRACT(ISODOW FROM local_now) = 6 THEN (local_now::date - 1)
          WHEN EXTRACT(ISODOW FROM local_now) = 7 AND local_now::time < TIME '19:00' THEN (local_now::date - 2)
          WHEN EXTRACT(ISODOW FROM local_now) = 7 AND local_now::time >= TIME '19:00' THEN (local_now::date + 1)
          WHEN EXTRACT(ISODOW FROM local_now) IN (1, 2, 3, 4) AND local_now::time >= TIME '19:00' THEN (local_now::date + 1)
          ELSE local_now::date
        END AS trade_date
      FROM session_clock
    ),
    session_bounds AS (
      SELECT
        trade_date,
        ((trade_date - 1)::timestamp + TIME '19:00') AT TIME ZONE 'America/Chicago' AS session_start_utc,
        (trade_date::timestamp + TIME '13:20') AT TIME ZONE 'America/Chicago' AS session_end_utc,
        LEAST(
          (trade_date::timestamp + TIME '13:20') AT TIME ZONE 'America/Chicago',
          ${nowExpression}
        ) AS session_cutoff_utc
      FROM session_context
    )
  `;
}
