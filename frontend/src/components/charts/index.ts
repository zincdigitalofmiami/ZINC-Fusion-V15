/**
 * TradingView-Grade Chart Components
 *
 * Institutional-quality visualizations with proper color palette
 * NO RECHARTS DEFAULTS - only TradingView colors
 */

// Core color system
export {
  default as TV,
  rechartsTheme,
  getAreaGradient,
  getSvgAreaGradient,
} from "@/lib/colors";

// Chart components
export { TechnicalGauge, MiniTechnicalGauge } from "./TechnicalGauge";
export { SeasonalsChart, MiniSeasonals } from "./SeasonalsChart";
export { PerformanceGrid, PerformanceRow } from "./PerformanceGrid";
export { ForwardCurve, MiniForwardCurve } from "./ForwardCurve";
export { RangeBar, DayRange } from "./RangeBar";
export { ContractHighlights, RelatedCommodities } from "./ContractHighlights";
