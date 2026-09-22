"use client";

import { useSyncExternalStore } from "react";
import type { LiveRiskRow } from "@/lib/data";

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

export default function LiveNow({ rows }: { rows: LiveRiskRow[] }) {
  // Avoid an SSR/static-export hydration mismatch: "now" at build time and
  // "now" at view time are different instants (this page is a static
  // export, viewed possibly days after it was built) — render nothing
  // time-dependent until mounted on the viewer's own clock.
  const mounted = useMounted();

  return (
    <section aria-labelledby="live-heading" className="max-w-5xl mx-auto px-5 pt-10 pb-2">
      <div className="flex items-center gap-2 mb-1">
        <h2 id="live-heading" className="font-sans font-semibold text-[17px] text-text-primary">
          Live now
        </h2>
        <span className="font-sans text-[11px] font-medium px-1.5 py-0.5 border border-text-primary text-text-primary">
          live
        </span>
      </div>
      <p className="font-sans text-[13px] text-text-muted mb-5 max-w-2xl">
        Streamed directly from the Alchemy WebSocket feed, scored against the same frozen
        clustering model as the historical data. UST doesn&apos;t appear here — it has no live
        pool activity to track.
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
    </section>
  );
}
