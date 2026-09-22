"use client";

import { useSyncExternalStore } from "react";
import type { LiveRiskRow, LivePricePoint } from "@/lib/data";
import RiskGauge from "./RiskGauge";
import LivePriceChart from "./LivePriceChart";

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
    <section aria-labelledby="live-heading" className="max-w-5xl mx-auto px-5 pt-10 pb-2">
      <div className="flex items-center gap-2 mb-1">
        <h2 id="live-heading" className="font-sans font-semibold text-[17px] text-text-primary">
          Live now
        </h2>
        <span className="flex items-center gap-1 font-sans text-[11px] font-medium px-1.5 py-0.5 border border-text-primary text-text-primary">
          <span className="w-1.5 h-1.5 rounded-full bg-accent animate-pulse" aria-hidden="true" />
          live
        </span>
      </div>
      <p className="font-sans text-[13px] text-text-muted mb-5 max-w-2xl">
        Every bar below is a live reading of the same 0–100 risk score used throughout this
        page, computed right now from real trades happening on-chain — not historical data.
        The marker on each bar shows where a real historical crisis has averaged, for scale.
        Streamed from a WebSocket feed of on-chain trades, scored against the same frozen
        model as the case studies below. UST doesn&apos;t appear here — it has no live pool
        activity to track (see the note at the bottom of this page).
      </p>

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
              className="bg-surface p-4 border-r border-b border-border basis-1/2 sm:basis-1/4 grow"
            >
              <div className="font-mono text-[11px] text-text-muted mb-2 truncate">
                {r.pair} · {r.project}
              </div>
              <div className="font-mono text-[26px] font-medium leading-none text-text-primary">
                {r.risk_score.toFixed(1)}
              </div>
              <RiskGauge score={r.risk_score} />
              <div className="mt-2 font-mono text-[10px] text-text-muted" suppressHydrationWarning>
                {mounted ? `updated ${relativeTime(r.window_start_ts)}` : " "}
              </div>
              <div className="mt-1 font-sans text-[10px] text-text-muted">
                {SOURCE_LABEL[r.source] ?? r.source}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="mt-8">
        <h3 className="font-sans font-semibold text-[14px] text-text-primary mb-1">
          Live price, as it&apos;s trading right now
        </h3>
        <p className="font-sans text-[12.5px] text-text-muted mb-4 max-w-2xl">
          Each finalized hourly window&apos;s implied price, updated as the streaming consumer
          emits new windows. Unlike the crisis charts below, the price axis here is zoomed to
          the actual range of live readings, not a fixed $0–$1.05 — a real crisis would still
          be unmistakable, but small day-to-day movement stays visible too.
        </p>
        <div className="flex flex-col sm:flex-row gap-8 sm:gap-10">
          {chartsData.map(({ pair, series }) => (
            <LivePriceChart key={pair} pair={pair} series={series} />
          ))}
        </div>
      </div>
    </section>
  );
}
