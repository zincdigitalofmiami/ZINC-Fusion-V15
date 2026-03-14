import type {
  AutoscaleInfo,
  Coordinate,
  IPrimitivePaneRenderer,
  IPrimitivePaneView,
  ISeriesPrimitive,
  SeriesAttachedParameter,
  SeriesType,
  Time,
} from "lightweight-charts";
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type { PivotLine, PivotTimeframe } from "@/lib/charts/pivots";

const STYLES = {
  pivotLineWidth: 2,
  levelLineWidth: 1,
  labelFont: '10px -apple-system, BlinkMacSystemFont, "Inter", sans-serif',
  labelPaddingX: 6,
  labelPaddingY: 3,
  lineAlpha: 0.6,
  pivotLineAlpha: 0.8,
} as const;

interface ResolvedPivot {
  price: number;
  label: string;
  level: string;
  startTime?: Time;
  color: string;
  isPivotPoint: boolean;
}

class PivotLinesRenderer implements IPrimitivePaneRenderer {
  private pivots: ResolvedPivot[] = [];
  private priceToY: ((price: number) => Coordinate | null) | null = null;
  private timeToX: ((time: Time) => Coordinate | null) | null = null;

  update(
    pivots: ResolvedPivot[],
    priceToY: (price: number) => Coordinate | null,
    timeToX: (time: Time) => Coordinate | null,
  ) {
    this.pivots = pivots;
    this.priceToY = priceToY;
    this.timeToX = timeToX;
  }

  draw(target: CanvasRenderingTarget2D): void {
    target.useMediaCoordinateSpace(({ context, mediaSize }) => {
      if (!this.priceToY || !this.timeToX) return;

      for (const pivot of this.pivots) {
        const y = this.priceToY(pivot.price);
        if (y == null) continue;
        if (y < -20 || y > mediaSize.height + 20) continue;

        const alpha = pivot.isPivotPoint
          ? STYLES.pivotLineAlpha
          : STYLES.lineAlpha;
        const lineWidth = pivot.isPivotPoint
          ? STYLES.pivotLineWidth
          : STYLES.levelLineWidth;

        const startXRaw =
          pivot.startTime != null ? this.timeToX(pivot.startTime) : 0;
        const startX = startXRaw == null ? 0 : Math.max(0, startXRaw);
        if (startX >= mediaSize.width) continue;

        context.strokeStyle = hexToRgba(pivot.color, alpha);
        context.lineWidth = lineWidth;
        context.setLineDash([]);
        context.beginPath();
        context.moveTo(startX, y);
        context.lineTo(mediaSize.width, y);
        context.stroke();

        context.font = STYLES.labelFont;
        context.fillStyle = hexToRgba(pivot.color, 0.9);
        context.textBaseline = "bottom";
        const labelY = y - STYLES.labelPaddingY + 1;
        if (startX > 56) {
          context.textAlign = "right";
          context.fillText(pivot.label, startX - 6, labelY);
        } else {
          context.textAlign = "left";
          context.fillText(pivot.label, startX + STYLES.labelPaddingX, labelY);
        }
        context.textAlign = "left";
      }
    });
  }
}

class PivotLinesPaneView implements IPrimitivePaneView {
  private rendererInstance = new PivotLinesRenderer();

  update(
    pivots: ResolvedPivot[],
    priceToY: (price: number) => Coordinate | null,
    timeToX: (time: Time) => Coordinate | null,
  ) {
    this.rendererInstance.update(pivots, priceToY, timeToX);
  }

  zOrder(): "top" {
    return "top";
  }

  renderer(): IPrimitivePaneRenderer {
    return this.rendererInstance;
  }
}

export class PivotLinesPrimitive implements ISeriesPrimitive<Time> {
  private pivots: PivotLine[] = [];
  private colors: Record<PivotTimeframe, string> = {
    D: "#FFFFFF",
    W: "#F23645",
    M: "#FFFFFF",
    Y: "#F23645",
  };
  private paneView = new PivotLinesPaneView();
  private attachedParams: SeriesAttachedParameter<Time, SeriesType> | null =
    null;

  setPivots(pivots: PivotLine[], colors?: Record<PivotTimeframe, string>) {
    this.pivots = pivots;
    if (colors) this.colors = colors;
    this.attachedParams?.requestUpdate();
  }

  attached(param: SeriesAttachedParameter<Time, SeriesType>) {
    this.attachedParams = param;
  }

  detached() {
    this.attachedParams = null;
  }

  updateAllViews() {
    if (!this.attachedParams) return;

    const { chart, series } = this.attachedParams;
    const resolved = this.pivots.map((pivot) => ({
      ...pivot,
      color: this.colors[pivot.timeframe] ?? "#F23645",
      isPivotPoint: pivot.level === "P",
    }));

    this.paneView.update(
      resolved,
      (price: number) => series.priceToCoordinate(price),
      (time: Time) => chart.timeScale().timeToCoordinate(time),
    );
  }

  paneViews(): readonly IPrimitivePaneView[] {
    return [this.paneView];
  }

  priceAxisViews(): readonly [] {
    return [];
  }

  autoscaleInfo(): AutoscaleInfo | null {
    return null;
  }
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}
