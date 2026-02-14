/**
 * ForecastTargetsPrimitive.ts
 *
 * Lightweight Charts v5 Series Primitive that draws forecast target zones
 * with price-axis labels using shaded zone areas representing
 * the model's probabilistic price targets as zone areas.
 *
 * Data contract (all real, all from database):
 *   - oofPrice  = price_p50  from forecasts.production_1d
 *   - priceLow  = price_p30  from forecasts.production_1d
 *   - priceHigh = price_p70  from forecasts.production_1d
 *   - mae       = from training.model_runs_event
 *   - probability metadata: Monte Carlo method + P30-P70 + coverage %
 *
 * Visual output per target:
 *   - Horizontal shaded rectangle from startTime → endTime at [priceLow, priceHigh]
 *   - Price-axis label: "TP1 21d 57.47 | MC P30-P70 40% | MAE ±0.80"
 */
import type {
  ISeriesPrimitive,
  SeriesAttachedParameter,
  Time,
  UTCTimestamp,
  IPrimitivePaneView,
  IPrimitivePaneRenderer,
  ISeriesPrimitiveAxisView,
  Logical,
  AutoscaleInfo,
  PrimitiveHoveredItem,
  DrawingUtils,
  IChartApiBase,
  ISeriesApi,
  SeriesType,
} from "lightweight-charts";
import type { CanvasRenderingTarget2D } from "fancy-canvas";

// ---------------------------------------------------------------------------
// Public types
// ---------------------------------------------------------------------------

export type TargetKind = "ENTRY" | "TP" | "SL";

export interface ForecastTarget {
  /** Unique identifier for this target (e.g. "tp-5d") */
  id: string;
  /** Visual classification */
  kind: TargetKind;
  /** Zone label: TP1, TP2, SL1, ... */
  label: string;
  /** Optional horizon display label (e.g., "21d") */
  horizonLabel?: string;
  /** Left edge of the zone (typically last-candle time) */
  startTime: UTCTimestamp;
  /** Right edge of the zone (forecast horizon date) */
  endTime: UTCTimestamp;
  /** Center of the zone — price_p50 from production_1d */
  oofPrice: number;
  /** Lower zone edge — price_p30 from production_1d */
  priceLow: number;
  /** Upper zone edge — price_p70 from production_1d */
  priceHigh: number;
  /** MAE from model_runs_event (null if unavailable) */
  mae: number | null;
  /** Probability metadata used for labels */
  probabilityMethod?: string;
  probabilityZone?: string;
  coveragePct?: number;
  /** ISO date string of the model's as_of_date (for staleness check) */
  asOfDate?: string;
  /** Horizon in calendar days — e.g. 5, 21, 63, 126 (for staleness check) */
  horizonDays?: number;
}

// ---------------------------------------------------------------------------
// Internal geometry
// ---------------------------------------------------------------------------

interface ZoneCoords {
  id: string;
  x1: number;
  x2: number;
  yTop: number;
  yBot: number;
  fill: string;
  stroke: string;
}

// ---------------------------------------------------------------------------
// Colors — soft institutional zones, not "hard calls"
// ---------------------------------------------------------------------------

function colors(kind: TargetKind): {
  fill: string;
  stroke: string;
  axisBack: string;
  axisText: string;
} {
  switch (kind) {
    case "TP":
      return {
        fill: "rgba(0, 200, 120, 0.20)",
        stroke: "rgba(0, 200, 120, 0.60)",
        axisBack: "rgba(0, 200, 120, 0.92)",
        axisText: "#0b0b0b",
      };
    case "SL":
      return {
        fill: "rgba(245, 158, 11, 0.20)",
        stroke: "rgba(245, 158, 11, 0.60)",
        axisBack: "rgba(245, 158, 11, 0.92)",
        axisText: "#0b0b0b",
      };
    case "ENTRY":
    default:
      return {
        fill: "rgba(80, 160, 255, 0.16)",
        stroke: "rgba(80, 160, 255, 0.50)",
        axisBack: "rgba(80, 160, 255, 0.90)",
        axisText: "#0b0b0b",
      };
  }
}

// ---------------------------------------------------------------------------
// Staleness detection — a forecast is "stale" when its age exceeds its horizon
// ---------------------------------------------------------------------------

/**
 * A forecast is "stale" when its age (calendar days since as_of_date) exceeds
 * its own horizon window.  E.g., a 5d forecast made 7 days ago is stale.
 * Returns false when optional fields are absent (safe default).
 */
function isStale(t: ForecastTarget): boolean {
  if (!t.asOfDate || !t.horizonDays) return false;
  const asOf = new Date(t.asOfDate);
  const now = new Date();
  const daysSince = Math.floor(
    (now.getTime() - asOf.getTime()) / (24 * 60 * 60 * 1000),
  );
  return daysSince > t.horizonDays;
}

/** Reduce opacity for stale targets — dims fill/stroke/axis while keeping text legible */
function staleAdjust(c: ReturnType<typeof colors>): typeof c {
  return {
    fill: c.fill.replace(/[\d.]+\)$/, "0.06)"),
    stroke: c.stroke.replace(/[\d.]+\)$/, "0.20)"),
    axisBack: c.axisBack.replace(/[\d.]+\)$/, "0.40)"),
    axisText: c.axisText,
  };
}

// ---------------------------------------------------------------------------
// Label formatting
// ---------------------------------------------------------------------------

function formatLabel(t: ForecastTarget): string {
  // MAE from model_runs_event, or fall back to zone half-width
  const errorVal = t.mae != null ? t.mae : (t.priceHigh - t.priceLow) / 2;
  const likelihood = Number.isFinite(t.coveragePct)
    ? `${t.coveragePct}% likely`
    : "";
  const horizonText = t.horizonLabel
    ? `${t.horizonLabel.replace("d", "-Day")} Target`
    : t.label;
  const accuracyText = `\u00b1$${errorVal.toFixed(2)} accuracy`;
  let label = likelihood
    ? `${horizonText} $${t.oofPrice.toFixed(2)}  \u00b7  ${likelihood}  \u00b7  ${accuracyText}`
    : `${horizonText} $${t.oofPrice.toFixed(2)}  \u00b7  ${accuracyText}`;
  if (isStale(t)) {
    label += "  STALE";
  }
  return label;
}

// ---------------------------------------------------------------------------
// Price-axis label view
// ---------------------------------------------------------------------------

class TargetAxisLabelView implements ISeriesPrimitiveAxisView {
  private _coordinate: number = -1e9;
  private _text: string = "";
  constructor(
    private _back: string,
    private _textColor: string,
  ) {}

  set(coordinate: number | null, text: string) {
    this._coordinate = coordinate ?? -1e9;
    this._text = text;
  }

  coordinate(): number {
    return this._coordinate;
  }
  text(): string {
    return this._text;
  }
  textColor(): string {
    return this._textColor;
  }
  backColor(): string {
    return this._back;
  }
  visible(): boolean {
    return this._coordinate > -1e8;
  }
  tickVisible(): boolean {
    return false;
  }
}

// ---------------------------------------------------------------------------
// Canvas renderer — draws the shaded zone rectangles
// ---------------------------------------------------------------------------

class TargetZonesRenderer implements IPrimitivePaneRenderer {
  private _zones: ZoneCoords[] = [];

  update(zones: ZoneCoords[]) {
    this._zones = zones;
  }

  draw(_target: CanvasRenderingTarget2D, _utils?: DrawingUtils): void {
    // Intentionally empty — all drawing deferred to drawBackground so zones
    // render behind the candles (correct z-order for an "area" overlay).
  }

  drawBackground(target: CanvasRenderingTarget2D, _utils?: DrawingUtils): void {
    target.useBitmapCoordinateSpace((scope) => {
      const ctx = scope.context;
      ctx.save();
      try {
        for (const z of this._zones) {
          const x = Math.round(z.x1 * scope.horizontalPixelRatio);
          const y = Math.round(z.yTop * scope.verticalPixelRatio);
          const w = Math.round((z.x2 - z.x1) * scope.horizontalPixelRatio);
          const h = Math.round((z.yBot - z.yTop) * scope.verticalPixelRatio);
          if (w <= 0 || h <= 0) continue;

          // Filled zone
          ctx.fillStyle = z.fill;
          ctx.fillRect(x, y, w, h);

          // Subtle border
          ctx.strokeStyle = z.stroke;
          ctx.lineWidth = Math.max(1, Math.round(1 * scope.verticalPixelRatio));
          ctx.strokeRect(x + 0.5, y + 0.5, w - 1, h - 1);
        }
      } finally {
        ctx.restore();
      }
    });
  }
}

// ---------------------------------------------------------------------------
// Pane view (wraps renderer)
// ---------------------------------------------------------------------------

class TargetZonesPaneView implements IPrimitivePaneView {
  private _renderer = new TargetZonesRenderer();

  zOrder(): "bottom" {
    return "bottom";
  }
  renderer(): IPrimitivePaneRenderer {
    return this._renderer;
  }
  update(zones: ZoneCoords[]) {
    this._renderer.update(zones);
  }
}

// ---------------------------------------------------------------------------
// Main primitive
// ---------------------------------------------------------------------------

export class ForecastTargetsPrimitive implements ISeriesPrimitive<Time> {
  private _chart: IChartApiBase<Time> | null = null;
  private _series: ISeriesApi<SeriesType, Time> | null = null;
  private _requestUpdate: (() => void) | null = null;

  private _targets: ForecastTarget[] = [];
  private _paneView = new TargetZonesPaneView();
  private _axisViews: TargetAxisLabelView[] = [];
  private _cachedAutoscale: AutoscaleInfo | null = null;

  constructor(targets: ForecastTarget[]) {
    this._targets = targets;
    this._rebuildAxisViews();
    this._rebuildAutoscaleCache();
  }

  /** Replace all targets and trigger a redraw */
  setTargets(targets: ForecastTarget[]) {
    this._targets = targets;
    this._rebuildAxisViews();
    this._rebuildAutoscaleCache();
    this._requestUpdate?.();
  }

  // ---- Lifecycle -----------------------------------------------------------

  attached(param: SeriesAttachedParameter<Time, SeriesType>): void {
    this._chart = param.chart;
    this._series = param.series;
    this._requestUpdate = param.requestUpdate;
  }

  detached(): void {
    this._chart = null;
    this._series = null;
    this._requestUpdate = null;
  }

  // ---- Views ---------------------------------------------------------------

  paneViews(): readonly IPrimitivePaneView[] {
    return [this._paneView];
  }

  priceAxisViews(): readonly ISeriesPrimitiveAxisView[] {
    return this._axisViews;
  }

  // ---- Coordinate conversion (called on every frame) -----------------------

  updateAllViews(): void {
    if (!this._chart || !this._series) return;

    const zones: ZoneCoords[] = [];

    for (let i = 0; i < this._targets.length; i++) {
      const t = this._targets[i];
      if (
        !Number.isFinite(t.priceHigh) ||
        !Number.isFinite(t.priceLow) ||
        !Number.isFinite(t.oofPrice)
      ) {
        this._axisViews[i]?.set(null, "");
        continue;
      }

      const x1 = this._chart
        .timeScale()
        .timeToCoordinate(t.startTime as unknown as Time);
      const x2 = this._chart
        .timeScale()
        .timeToCoordinate(t.endTime as unknown as Time);
      if (x1 == null || x2 == null) {
        this._axisViews[i]?.set(null, "");
        continue;
      }

      const yTop = this._series.priceToCoordinate(t.priceHigh);
      const yBot = this._series.priceToCoordinate(t.priceLow);
      if (yTop == null || yBot == null) {
        this._axisViews[i]?.set(null, "");
        continue;
      }

      const top = Math.min(yTop, yBot);
      const bot = Math.max(yTop, yBot);

      const staleFlag = isStale(t);
      const c = staleFlag ? staleAdjust(colors(t.kind)) : colors(t.kind);
      zones.push({
        id: t.id,
        x1: Math.min(x1, x2),
        x2: Math.max(x1, x2),
        yTop: top,
        yBot: bot,
        fill: c.fill,
        stroke: c.stroke,
      });

      const midY = this._series.priceToCoordinate(t.oofPrice);
      this._axisViews[i]?.set(midY, formatLabel(t));
    }

    this._paneView.update(zones);
  }

  // ---- Autoscale (expand visible range to keep targets on-screen) ----------

  autoscaleInfo(
    _startLogical: Logical,
    _endLogical: Logical,
  ): AutoscaleInfo | null {
    return this._cachedAutoscale;
  }

  // ---- Hit test (no-op for now) --------------------------------------------

  hitTest(_x: number, _y: number): PrimitiveHoveredItem | null {
    return null;
  }

  // ---- Internal helpers ----------------------------------------------------

  private _rebuildAxisViews() {
    this._axisViews = this._targets.map((t) => {
      const staleFlag = isStale(t);
      const c = staleFlag ? staleAdjust(colors(t.kind)) : colors(t.kind);
      return new TargetAxisLabelView(c.axisBack, c.axisText);
    });
  }

  private _rebuildAutoscaleCache() {
    if (this._targets.length === 0) {
      this._cachedAutoscale = null;
      return;
    }
    const lows = this._targets
      .map((t) => t.priceLow)
      .filter((v) => Number.isFinite(v));
    const highs = this._targets
      .map((t) => t.priceHigh)
      .filter((v) => Number.isFinite(v));
    if (lows.length === 0 || highs.length === 0) {
      this._cachedAutoscale = null;
      return;
    }

    const minValue = Math.min(...lows);
    const maxValue = Math.max(...highs);

    this._cachedAutoscale = { priceRange: { minValue, maxValue } };
  }
}
