// frontend/src/components/policy/types.ts

export interface LegislationEvent {
  id: number;
  event_date: string; // ISO date string
  document_number: string | null;
  title: string | null;
  agency: string | null;
  document_type: string | null;
  action: string | null;
  specialist_tags: string[];
  url: string | null;
  source: string | null;
}

export interface ExecutiveEvent {
  id: number;
  event_date: string;
  headline: string;
  content: string | null;
  url: string | null;
  document_type: string | null;
  zl_sentiment: string | null;
  specialist_tags: string[];
  // Joined fields for "Shockwave" analysis
  zl_price_change?: number | null;
  zl_price_close?: number | null;
  price_return_1d?: number | null;
}

export interface TariffDeadline {
  id: number;
  deadline_name: string;
  deadline_date: string;
  days_to_expiry: number;
  renewal_probability: number | null;
  policy_type: string | null;
  description: string | null;
  is_active: boolean | null;
}

export interface AgencyActivity {
  agency: string;
  count: number;
  sentiment_score: number;
}

export interface TrumpEffectMetric {
  date: string;
  velocity: number | null;
  acceleration: number | null;
  score: number | null;
}

export interface PolicyUncertaintyIndex {
  date: string;
  value: number;
  series_id: string;
}

// Derived strictly for UI state/scoring (not a table)
export interface RegimeState {
  score: number; // 0-100 Threat Score
  label:
    | "Minimal"
    | "Background Noise"
    | "Elevated"
    | "Retaliation Risk"
    | "Active War";
  components: {
    tpu: number; // Trade Policy Uncertainty Index
    emv: number; // Equity Market Volatility (Trade)
    news_velocity: number; // Count of recent news
    legis_velocity: number; // Count of recent bills
  };
}
