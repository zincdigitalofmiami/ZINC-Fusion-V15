/**
 * Market Intelligence Narrative Generator
 *
 * Produces plain-English market summaries for Vegas buyers.
 * Pure function — no DB access, no side effects.
 */

// =============================================================================
// TYPES
// =============================================================================

export interface DriverResult {
  score: number;
  level: string;
  regime: string;
  headline: string;
}

// =============================================================================
// NARRATIVE GENERATOR
// =============================================================================

export function generateMarketIntelligence(
  vix: DriverResult,
  _vixValue: number,
  crush: DriverResult,
  crushValue: number,
  oilShare: number | null,
  china: DriverResult,
  cnyRate: number,
  _hgChange20d: number,
  tariff: DriverResult,
  _tpuValue: number,
  energy?: DriverResult,
): {
  headline: string;
  summary: string;
  drivers: { label: string; outlook: string; detail: string }[];
  zlOutlook: "BULLISH" | "NEUTRAL" | "CAUTIOUS" | "BEARISH";
  zlColor: string;
} {
  const allScores = [vix.score, crush.score, china.score, tariff.score];
  if (energy) allScores.push(energy.score);
  const avgScore = allScores.reduce((a, b) => a + b, 0) / allScores.length;
  const highPressureCount = allScores.filter((s) => s >= 65).length;
  const lowPressureCount = allScores.filter((s) => s <= 35).length;

  let zlOutlook: "BULLISH" | "NEUTRAL" | "CAUTIOUS" | "BEARISH";
  let zlColor: string;
  let headline: string;

  // VEGAS BUYER LANGUAGE - DIRECT AND ACTIONABLE
  if (avgScore >= 70 || highPressureCount >= 3) {
    zlOutlook = "BEARISH";
    zlColor = "#EF4444";
    headline = "WAIT TO BUY - Multiple Red Flags";
  } else if (avgScore >= 55 || highPressureCount >= 2) {
    zlOutlook = "CAUTIOUS";
    zlColor = "#F97316";
    headline = "CAUTION - Mixed Signals, Keep Powder Dry";
  } else if (avgScore >= 40) {
    zlOutlook = "NEUTRAL";
    zlColor = "#EAB308";
    headline = "NORMAL MARKET - Buy On Schedule";
  } else {
    zlOutlook = "BULLISH";
    zlColor = "#22C55E";
    headline = "GOOD WINDOW - Lock In Coverage";
  }

  // BUILD PLAIN ENGLISH SUMMARY FOR VEGAS BUYERS
  const summaryParts: string[] = [];

  // Lead with the action
  if (avgScore >= 65) {
    summaryParts.push(`Bottom line: HOLD OFF on new purchases.`);
  } else if (avgScore <= 35) {
    summaryParts.push(`Bottom line: Good time to cover your needs.`);
  } else {
    summaryParts.push(`Bottom line: Normal market conditions.`);
  }

  // Volatility - simple
  if (vix.score >= 65) {
    summaryParts.push(`Wall Street is panicking - prices could swing wildly.`);
  } else if (vix.score <= 35) {
    summaryParts.push(`Markets are calm - stable pricing environment.`);
  }

  // Crush - what it means for supply
  if (crush.score >= 65) {
    summaryParts.push(
      `Crushers struggling at $${crushValue.toFixed(2)}/bu margins - supply may tighten.`,
    );
  } else if (crush.score <= 35) {
    summaryParts.push(
      `Crushers making money at $${crushValue.toFixed(2)}/bu - plenty of oil supply.`,
    );
  }

  // China
  if (china.score >= 65) {
    summaryParts.push(
      `China demand pulse is weak - global buying flow is not providing support.`,
    );
  } else {
    summaryParts.push(
      `China demand is stable but not a major upside catalyst right now.`,
    );
  }

  // Macro threat (Iran war, inflation, oil, uncertainty, VIX, news)
  if (tariff.score >= 65) {
    summaryParts.push(`Macro threat is high - geopolitical and oil-risk headlines can reprice ZL quickly.`);
  } else if (tariff.score <= 35) {
    summaryParts.push(`Macro backdrop is contained - no immediate shock signal.`);
  }

  // Energy - crude oil / biofuel channel
  if (energy) {
    if (energy.score >= 80) {
      summaryParts.push(`ENERGY CRISIS - crude oil surging, biofuel costs spiking. Soy oil being diverted to renewable diesel.`);
    } else if (energy.score >= 65) {
      summaryParts.push(`Oil supply shock underway - energy costs rising, pushing biofuel economics into soy oil.`);
    } else if (energy.score >= 50) {
      summaryParts.push(`Energy markets running hot - watch crude oil for biofuel demand spillover.`);
    } else if (energy.score <= 35) {
      summaryParts.push(`Energy markets calm - falling crude eases biofuel pressure on soy oil.`);
    }
  }

  // Final recommendation
  if (highPressureCount >= 2) {
    summaryParts.push(
      `RECOMMENDATION: Wait for better entry. Too many headwinds right now.`,
    );
  } else if (lowPressureCount >= 3) {
    summaryParts.push(
      `RECOMMENDATION: Lock in coverage. Conditions favor buyers.`,
    );
  } else {
    summaryParts.push(
      `RECOMMENDATION: Normal buying on your schedule. Nothing dramatic either way.`,
    );
  }

  const drivers = [
    {
      label: "Markets",
      outlook:
        vix.score >= 65
          ? "PANIC"
          : vix.score >= 50
            ? "NERVOUS"
            : vix.score <= 35
              ? "CALM"
              : "OK",
      detail:
        vix.score >= 65
          ? "Funds selling everything"
          : vix.score <= 35
            ? "Stable, fundamentals-driven"
            : "Normal volatility",
    },
    {
      label: "Crush",
      outlook:
        crush.score >= 65 ? "TIGHT" : crush.score <= 35 ? "FLUSH" : "NORMAL",
      detail: `$${crushValue.toFixed(2)}/bu margins - ${crush.score >= 65 ? "plants slowing" : crush.score <= 35 ? "running full out" : "normal pace"}`,
    },
    {
      label: "China",
      outlook: china.score >= 65 ? "FROZEN" : "BRAZIL WINS",
      detail:
        china.score >= 65
          ? "Trade disrupted"
          : `Brazil preferred at 13% tariff gap`,
    },
    {
      label: "Macro",
      outlook:
        tariff.score >= 65 ? "ALERT" : tariff.score <= 35 ? "CALM" : "WATCH",
      detail:
        tariff.score >= 65
          ? "Iran/uncertainty/oil risk elevated"
          : tariff.score <= 35
            ? "Contained macro backdrop"
            : "Macro headlines mixed",
    },
    ...(energy
      ? [
          {
            label: "Energy",
            outlook:
              energy.score >= 80
                ? "CRISIS"
                : energy.score >= 65
                  ? "SHOCK"
                  : energy.score >= 50
                    ? "HOT"
                    : energy.score <= 35
                      ? "CALM"
                      : "OK",
            detail:
              energy.score >= 65
                ? "Crude surging — biofuel costs up"
                : energy.score <= 35
                  ? "Energy calm — no pressure"
                  : "Energy steady",
          },
        ]
      : []),
  ];

  return {
    headline,
    summary: summaryParts.join(" "),
    drivers,
    zlOutlook,
    zlColor,
  };
}
