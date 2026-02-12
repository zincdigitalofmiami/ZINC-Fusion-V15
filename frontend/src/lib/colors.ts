/**
 * ZINC FUSION V15 - TradingView-Grade Color System
 *
 * NO RECHARTS DEFAULTS. These are institutional-grade colors.
 * Source: TradingView dark theme + professional trading terminals
 *
 * "uglier than the back of my nuts" - Kirk, on recharts colors
 */

// =============================================================================
// CORE PALETTE - TradingView Exact
// =============================================================================

export const TV = {
  // Backgrounds
  bg: {
    primary: "#131722", // Main background
    secondary: "#1e222d", // Card background
    tertiary: "#2a2e39", // Elevated elements
    hover: "#363a45", // Hover states
  },

  // Text
  text: {
    primary: "#d1d4dc", // Main text
    secondary: "#787b86", // Muted text
    tertiary: "#434651", // Very muted
    inverse: "#131722", // For light backgrounds
  },

  // Borders
  border: {
    primary: "rgba(255, 255, 255, 0.1)",
    secondary: "rgba(255, 255, 255, 0.05)",
    accent: "rgba(255, 255, 255, 0.2)",
  },

  // ==========================================================================
  // SEMANTIC COLORS - Trading Signals
  // ==========================================================================

  // Bullish / Up / Buy
  bull: {
    primary: "#26a69a", // Main teal
    bright: "#22ab94", // Brighter teal
    light: "#00c853", // Green accent
    muted: "rgba(38, 166, 154, 0.2)",
    gradient:
      "linear-gradient(180deg, rgba(38, 166, 154, 0.4) 0%, rgba(38, 166, 154, 0) 100%)",
  },

  // Bearish / Down / Sell
  bear: {
    primary: "#ef5350", // Main red
    bright: "#f23645", // Brighter red
    light: "#ff5252", // Light red
    muted: "rgba(239, 83, 80, 0.2)",
    gradient:
      "linear-gradient(180deg, rgba(239, 83, 80, 0) 0%, rgba(239, 83, 80, 0.4) 100%)",
  },

  // Neutral
  neutral: {
    primary: "#787b86",
    light: "#9598a1",
    muted: "rgba(120, 123, 134, 0.2)",
  },

  // ==========================================================================
  // ACCENT COLORS
  // ==========================================================================

  blue: {
    primary: "#2962ff", // TradingView blue
    bright: "#3d7aff",
    muted: "rgba(41, 98, 255, 0.2)",
  },

  purple: {
    primary: "#7b1fa2",
    bright: "#9c27b0",
    muted: "rgba(123, 31, 162, 0.2)",
  },

  orange: {
    primary: "#ff9800",
    bright: "#ffb74d",
    muted: "rgba(255, 152, 0, 0.2)",
  },

  cyan: {
    primary: "#00bcd4",
    bright: "#26c6da",
    muted: "rgba(0, 188, 212, 0.2)",
  },

  // ==========================================================================
  // FORECAST TARGET ZONE COLORS (horizontal zones on LWC chart)
  // ==========================================================================

  forecast: {
    max: "#22ab94", // Green - upper target bound
    avg: "#ffb74d", // Orange/yellow - P50 expected
    current: "#26a69a", // Teal - current price
    min: "#f06292", // Pink/red - lower target bound

    // Zone fill colors
    maxFill: "rgba(34, 171, 148, 0.15)",
    minFill: "rgba(240, 98, 146, 0.15)",

    // Projection line
    projectionLine: "#787b86",
    projectionDash: "4 2",
  },

  // ==========================================================================
  // GAUGE COLORS (Technicals meter)
  // ==========================================================================

  gauge: {
    strongSell: "#f23645", // Deep red
    sell: "#ff5252", // Light red
    neutral: "#787b86", // Gray
    buy: "#26a69a", // Teal
    strongBuy: "#22ab94", // Bright teal

    // Gradient stops for the arc
    gradient: [
      { offset: 0, color: "#f23645" }, // Strong sell
      { offset: 0.25, color: "#ff5252" }, // Sell
      { offset: 0.5, color: "#787b86" }, // Neutral
      { offset: 0.75, color: "#26a69a" }, // Buy
      { offset: 1, color: "#22ab94" }, // Strong buy
    ],
  },

  // ==========================================================================
  // SEASONALS / MULTI-YEAR OVERLAY
  // ==========================================================================

  years: {
    current: "#2962ff", // 2026 - Blue
    prev1: "#26a69a", // 2025 - Teal/Green
    prev2: "#ff9800", // 2024 - Orange
    prev3: "#9c27b0", // 2023 - Purple
  },

  // ==========================================================================
  // PERFORMANCE GRID
  // ==========================================================================

  perf: {
    positive: "#26a69a",
    negative: "#ef5350",
    neutral: "#787b86",
    bg: "rgba(255, 255, 255, 0.05)",
  },

  // ==========================================================================
  // SPECIALIST DRIVERS (for parallel coordinates)
  // ==========================================================================

  drivers: {
    crush: "#ff9800", // Orange
    china: "#f44336", // Red
    fx: "#2196f3", // Blue
    fed: "#9c27b0", // Purple
    tariff: "#e91e63", // Pink
    energy: "#ff5722", // Deep orange
    biofuel: "#4caf50", // Green
    palm: "#8bc34a", // Light green
    volatility: "#ffc107", // Amber
    substitutes: "#00bcd4", // Cyan
    trump: "#f44336", // Red (high impact)
  },
} as const;

// =============================================================================
// CHART AREA GRADIENTS (like TradingView area charts)
// =============================================================================

export function getAreaGradient(color: string, opacity: number = 0.4): string {
  return `linear-gradient(180deg, ${color}${Math.round(opacity * 255)
    .toString(16)
    .padStart(2, "0")} 0%, ${color}00 100%)`;
}

// For SVG gradients
export function getSvgAreaGradient(id: string, color: string): string {
  return `
    <linearGradient id="${id}" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" style="stop-color:${color};stop-opacity:0.4" />
      <stop offset="100%" style="stop-color:${color};stop-opacity:0" />
    </linearGradient>
  `;
}

// =============================================================================
// TAILWIND CSS VARIABLES (for globals.css)
// =============================================================================

export const cssVariables = `
  :root {
    /* TradingView Palette */
    --tv-bg-primary: #131722;
    --tv-bg-secondary: #1e222d;
    --tv-bg-tertiary: #2a2e39;

    --tv-text-primary: #d1d4dc;
    --tv-text-secondary: #787b86;

    --tv-bull: #26a69a;
    --tv-bull-bright: #22ab94;
    --tv-bear: #ef5350;
    --tv-bear-bright: #f23645;

    --tv-blue: #2962ff;
    --tv-orange: #ff9800;
    --tv-purple: #7b1fa2;
    --tv-cyan: #00bcd4;

    /* Forecast Target Zones */
    --tv-forecast-max: #22ab94;
    --tv-forecast-avg: #ffb74d;
    --tv-forecast-min: #f06292;
  }
`;

// =============================================================================
// RECHARTS OVERRIDE (force TradingView colors)
// =============================================================================

export const rechartsTheme = {
  // Override default colors
  colors: [
    TV.bull.primary,
    TV.bear.primary,
    TV.blue.primary,
    TV.orange.primary,
    TV.purple.primary,
    TV.cyan.primary,
  ],

  // Axis styling
  axis: {
    stroke: TV.border.primary,
    tick: { fill: TV.text.secondary },
    label: { fill: TV.text.secondary },
  },

  // Grid
  grid: {
    stroke: TV.border.secondary,
    strokeDasharray: "3 3",
  },

  // Tooltip
  tooltip: {
    contentStyle: {
      backgroundColor: TV.bg.secondary,
      border: `1px solid ${TV.border.primary}`,
      borderRadius: "4px",
    },
    labelStyle: { color: TV.text.primary },
    itemStyle: { color: TV.text.secondary },
  },
};

export default TV;
