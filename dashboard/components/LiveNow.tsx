"use client";

import { useSyncExternalStore } from "react";
import type { LiveRiskRow, LivePricePoint } from "@/lib/data";
import RiskGauge from "./RiskGauge";
import LivePriceChart from "./LivePriceChart";
import InfoTip from "./InfoTip";
import { HowToRead, ProcessTags, WhatIsThis } from "./Explain";

// The idiomatic way to detect "has this mounted on the client" — avoids
// the effect+setState anti-pattern (which can cascade renders) entirely,
// since useSyncExternalStore is literally designed for a value that
// legitimately differs between server render and client render.
const noopSubscribe = () => () => {};
function useMounted(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}

// Computed client-side, on the viewer's own clock, at view time — not at
// build/export time, which could be hours or days before someone actually
// loads the page (this is a static export). Handles the "stale but real"
// case honestly: a row that's genuinely hours old says so plainly, the
// same honesty standard as the zero-data empty state below.
function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const now = Date.now();
  const diffMin = Math.round((now - then) / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.round(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hour${diffHr === 1 ? "" : "s"} ago`;
  const diffDay = Math.round(diffHr / 24);
  return `${diffDay} day${diffDay === 1 ? "" : "s"} ago`;
}

const SOURCE_LABEL: Record<string, string> = {
  alchemy_live: "live",
  alchemy_getlogs_replay: "gap-filled",
};

function SourceBadge({ source }: { source: string }) {
  const label = SOURCE_LABEL[source] ?? source;
  const live = source === "alchemy_live";
  return (
    <span
      className={`inline-flex items-center border px-1.5 py-0.5 font-sans text-[11px] font-medium leading-none ${
        live ? "border-accent text-accent" : "border-text-muted text-text-secondary"
      }`}
    >
      {label}
    </span>
  );
}

function SignalLine({
  name,
  value,
  weight,
  tip,
}: {
  name: string;
  value: string;
  weight: string;
  tip: "priceDev" | "clusterSeverity" | "walletConc";
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 font-mono text-[11px]">
      <dt className="text-text-muted whitespace-nowrap">
        {name}
        <InfoTip k={tip} label={name} />
      </dt>
      <dd className="text-text-primary font-tabular whitespace-nowrap">
        {value} <span className="text-text-muted">· {weight}</span>
      </dd>
    </div>
  );
}

export default function LiveNow({
  rows,
  priceTimeline,
}: {
  rows: LiveRiskRow[];
  priceTimeline: LivePricePoint[];
}) {
  // Avoid an SSR/static-export hydration mismatch: "now" at build time and
  // "now" at view time are different instants (this page is a static
  // export, viewed possibly days after it was built) — render nothing
  // time-dependent until mounted on the viewer's own clock.
  const mounted = useMounted();

  // Live tracking is USDC-only (see spark/stream_alchemy_live.scala) —
  // exactly two pairs, each on two DEXs, confirmed grouping (one chart per
  // pair, two lines each) rather than one combined chart or four separate
  // ones.
  const byPair = (pair: string) => ({
    pair,
    series: [
      { label: "curve", dash: false, points: priceTimeline.filter((p) => p.pair === pair && p.project === "curve") },
      { label: "uniswap_v2", dash: true, points: priceTimeline.filter((p) => p.pair === pair && p.project === "uniswap_v2") },
    ],
  });
  const chartsData = [byPair("USDC_DAI"), byPair("USDC_USDT")];

  return (
    <section id="live-now" aria-labelledby="live-heading" className="max-w-5xl mx-auto px-5 pt-10 pb-2 scroll-mt-4">
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <h2 id="live-heading" className="font-sans font-semibold text-[17px] text-text-primary">
          Live now
        </h2>
        <span className="flex items-center gap-1 font-sans text-[11px] font-medium px-1.5 py-0.5 border border-text-primary text-text-primary">
          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" aria-hidden="true" />
          live
        </span>
        <ProcessTags types={["streaming", "ml"]} />
        <InfoTip k="riskScore" label="Risk score (0–100)" />
      </div>
      <WhatIsThis className="mb-2">
        The newest hourly stress score for each live pool, computed from real Ethereum trades
        by Spark Structured Streaming and scored with the same frozen K-Means model as the case
        studies below. UST doesn&apos;t appear here — it has no live pool activity to track.
      </WhatIsThis>
      <HowToRead className="mb-5">
        Each card is one pool (pair · exchange). The big number is the 0–100 score; the bar
        shows it on that scale and the thin line marks where USDC&apos;s real crisis averaged.
        Underneath, three of the four sub-signals show their value and weight in the score.
        Volume / trade anomaly (weight 0.25) is the fourth.
        <InfoTip k="volumeAnomaly" label="Volume / trade anomaly" />
      </HowToRead>

      {rows.length === 0 ? (
        <div className="border border-border p-4">
          <p className="font-sans text-[13px] text-text-muted">
            No live readings yet — the streaming consumer started recently; check back shortly.
          </p>
        </div>
      ) : (
        <div className="flex flex-wrap border-t border-l border-border">
          {rows.map((r) => (
            <div
              key={`${r.pair}-${r.project}`}
              className="bg-surface p-4 border-r border-b border-border basis-full sm:basis-1/2 lg:basis-1/4 grow"
            >
              <div className="font-mono text-[11px] text-text-muted mb-2 truncate">
                {r.pair} · {r.project}
              </div>
              <div className="font-mono text-[26px] font-medium leading-none text-text-primary">
                {r.risk_score.toFixed(4)}
              </div>
              <RiskGauge score={r.risk_score} />
              <div className="mt-1 font-sans text-[10.5px] text-text-muted">
                score bar
                <InfoTip k="scoreBar" label="Score bar and crisis marker" />
              </div>

              <dl className="mt-3 space-y-1 border-t border-border pt-2">
                {r.price_dev != null && (
                  <SignalLine
                    name="price dev."
                    value={`${r.price_dev.toFixed(2)} σ`}
                    weight="40%"
                    tip="priceDev"
                  />
                )}
                {r.cluster_severity != null && (
                  <SignalLine
                    name="cluster sev."
                    value={r.cluster_severity.toFixed(2)}
                    weight="15%"
                    tip="clusterSeverity"
                  />
                )}
                {r.wallet_concentration_severity != null && (
                  <SignalLine
                    name="wallet conc."
                    value={r.wallet_concentration_severity.toFixed(3)}
                    weight="20%"
                    tip="walletConc"
                  />
                )}
              </dl>

              <div className="mt-3 flex flex-wrap items-center gap-x-2 gap-y-1">
                <SourceBadge source={r.source} />
                <InfoTip k="sourceLive" label="live vs gap-filled" />
              </div>
              <div className="mt-1.5 font-mono text-[10px] text-text-muted" suppressHydrationWarning>
                {mounted ? `window began ${relativeTime(r.window_start_ts)}` : " "}
                <InfoTip k="updated" label="Window start time" />
              </div>
              {r.advisory && (
                <p className="mt-3 border-t border-border pt-3 font-sans text-[12px] leading-relaxed text-text-primary">
                  {r.advisory}
                </p>
              )}
            </div>
          ))}
        </div>
      )}

      <div className="mt-8">
        <div className="flex flex-wrap items-center gap-2 mb-1">
          <h3 className="font-sans font-semibold text-[15px] text-text-primary">
            Live price, as it&apos;s trading right now
          </h3>
          <ProcessTags types={["streaming"]} />
          <InfoTip k="livePrice" label="Hourly implied price" />
        </div>
        <WhatIsThis className="mb-1">
          The price implied by each finalized hourly window of swaps (tokens received ÷ tokens
          sent, so about $1.00 when the two coins trade one-for-one), one line per exchange pool.
        </WhatIsThis>
        <HowToRead className="mb-4">
          X axis: time (local date and hour). Y axis: implied price in dollars, zoomed to the
          actual range of live readings rather than the fixed $0–$1.05 of the crisis charts.
          Solid line = Curve, dashed line = Uniswap V2. Hover a point: the readout includes how many dollars traded that hour, so you can tell a spike on a few cents of volume (noise) from a move on real volume. A real depeg would still be unmistakable.
        </HowToRead>
        <div className="flex flex-col sm:flex-row gap-8 sm:gap-10">
          {chartsData.map(({ pair, series }) => (
            <LivePriceChart key={pair} pair={pair} series={series} />
          ))}
        </div>
      </div>
    </section>
  );
}
