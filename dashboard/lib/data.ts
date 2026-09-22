import fs from "fs";
import path from "path";

const DATA_DIR = path.join(process.cwd(), "data");

function readJson<T>(name: string): T {
  const raw = fs.readFileSync(path.join(DATA_DIR, name), "utf-8");
  return JSON.parse(raw) as T;
}

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

export function getCurrentRisk(): CurrentRiskRow[] {
  return readJson<CurrentRiskRow[]>("current_risk.json");
}

export function getLiveRisk(): LiveRiskRow[] {
  return readJson<LiveRiskRow[]>("current_risk_live.json");
}

export function getUsdcTimeline(): TimelinePoint[] {
  return readJson<TimelinePoint[]>("usdc_crisis_timeline.json");
}

export function getUstTimeline(): TimelinePoint[] {
  return readJson<TimelinePoint[]>("ust_crisis_timeline.json");
}

export function getClassifierMetrics(): ClassifierMetricRow[] {
  return readJson<ClassifierMetricRow[]>("classifier_metrics.json");
}

export function getWalletRankings(): WalletRankingRow[] {
  return readJson<WalletRankingRow[]>("wallet_rankings.json");
}

export function getMetadata(): Metadata {
  return readJson<Metadata>("metadata.json");
}
