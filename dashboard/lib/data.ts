// Reads dashboard data from the Render backend (backend/main.py), which
// reads from Supabase (populated by ingestion/push_to_supabase.py) —
// replaces the earlier static-JSON-at-build-time approach. Design
// confirmed before implementing (see docs/ARCHITECTURE.md's Application Layer
// section for the full report): fetched from Server Components
// (server-to-server, Vercel -> Render, never the browser), so no CORS is
// needed, with a 60s revalidate window — reflects new data automatically
// without a rebuild, without hitting Render/Supabase on every page view.
//
// One combined fetch, not seven — Next.js automatically dedupes identical
// fetch() calls (same URL + options) within a render, so each getter
// below can call getDashboardData() independently and only one real
// network request happens per page render.

const RENDER_API_URL = process.env.RENDER_API_URL;

export type CurrentRiskRow = {
  pair: string;
  project: string;
  baseline_status: "RELIABLE" | "NO_RELIABLE_BASELINE";
  risk_score: number;
  dt: string;
  window_start_ts: string;
};

export type TimelinePoint = {
  window_start_ts: string;
  implied_price: number;
  volume_usd: number;
};

export type LivePricePoint = {
  pair: string;
  project: string;
  window_start_ts: string;
  implied_price: number;
  volume_usd: number;
};

export type ClassifierMetricRow = {
  direction: "TEST_ON_UST" | "TEST_ON_USDC";
  scorer: "logistic_regression" | "random_forest" | "rule_based_baseline";
  n_test: number;
  n_test_crisis: number;
  precision_crisis: number;
  recall_crisis: number;
  f1_crisis: number;
  pr_auc: number;
  threshold_used: number;
};

export type WalletRankingRow = {
  window_label: "USDC_MAR2023_CRISIS" | "UST_MAY2022_CRISIS";
  node_id: string;
  pagerank_score: number;
  rank_within_window: number;
  is_contract: boolean;
  label: string | null;
};

export type LiveRiskRow = {
  pair: string;
  project: string;
  risk_score: number;
  window_start_ts: string;
  source: "alchemy_live" | "alchemy_getlogs_replay";
};

export type Metadata = {
  exported_at: string;
  dataset_end_usdc: string;
  dataset_end_ust: string;
  usdc_crisis_window: [string, string];
  ust_crisis_window: [string, string];
};

type DashboardData = {
  current_risk: CurrentRiskRow[];
  current_risk_live: LiveRiskRow[];
  usdc_crisis_timeline: TimelinePoint[];
  ust_crisis_timeline: TimelinePoint[];
  live_price_timeline: LivePricePoint[];
  classifier_metrics: ClassifierMetricRow[];
  wallet_rankings: WalletRankingRow[];
  metadata: Metadata;
};

async function getDashboardData(): Promise<DashboardData> {
  if (!RENDER_API_URL) {
    throw new Error(
      "RENDER_API_URL is not set — this must be configured as a Vercel environment variable, " +
        "pointing at the deployed Render backend (e.g. https://meridian-api.onrender.com)."
    );
  }
  const res = await fetch(`${RENDER_API_URL}/api/dashboard-data`, {
    next: { revalidate: 60 },
  });
  if (!res.ok) {
    throw new Error(`Render backend returned ${res.status}: ${await res.text()}`);
  }
  return res.json();
}

export async function getCurrentRisk(): Promise<CurrentRiskRow[]> {
  return (await getDashboardData()).current_risk;
}

export async function getLiveRisk(): Promise<LiveRiskRow[]> {
  return (await getDashboardData()).current_risk_live;
}

export async function getUsdcTimeline(): Promise<TimelinePoint[]> {
  return (await getDashboardData()).usdc_crisis_timeline;
}

export async function getUstTimeline(): Promise<TimelinePoint[]> {
  return (await getDashboardData()).ust_crisis_timeline;
}

export async function getLivePriceTimeline(): Promise<LivePricePoint[]> {
  // Defaults to [] rather than trusting the field exists — unlike the
  // other fields here, this one can legitimately be absent for a real,
  // transitional reason: it only exists once both the Supabase table
  // (supabase/schema.sql) and the Render backend (backend/main.py) have
  // been updated and redeployed, which doesn't happen atomically with a
  // frontend deploy. Missing data degrades to LivePriceChart's own empty
  // state instead of crashing the whole page.
  return (await getDashboardData()).live_price_timeline ?? [];
}

export async function getClassifierMetrics(): Promise<ClassifierMetricRow[]> {
  return (await getDashboardData()).classifier_metrics;
}

export async function getWalletRankings(): Promise<WalletRankingRow[]> {
  return (await getDashboardData()).wallet_rankings;
}

export async function getMetadata(): Promise<Metadata> {
  return (await getDashboardData()).metadata;
}
