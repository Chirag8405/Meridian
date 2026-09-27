"use client";

import { useSyncExternalStore } from "react";
import type { RecentSwapEvent } from "@/lib/data";

const noopSubscribe = () => () => {};

function useMounted(): boolean {
  return useSyncExternalStore(noopSubscribe, () => true, () => false);
}

function relativeTime(iso: string): string {
  const diffMinutes = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (diffMinutes < 1) return "just now";
  if (diffMinutes < 60) return `${diffMinutes} min ago`;
  const diffHours = Math.round(diffMinutes / 60);
  return `${diffHours} hour${diffHours === 1 ? "" : "s"} ago`;
}

function poolLabel(event: RecentSwapEvent): string {
  if (event.pool_name === "curve_3pool") return "Curve 3pool";
  if (event.pool_name === "uniswap_v2_usdc_usdt") return "Uniswap V2 · USDC/USDT";
  if (event.pool_name === "uniswap_v2_usdc_dai") return "Uniswap V2 · USDC/DAI";
  return event.pool_name;
}

const sourceLabel: Record<RecentSwapEvent["source"], string> = {
  alchemy_live: "live",
  alchemy_getlogs_replay: "gap-filled",
};

export default function RecentActivity({ events }: { events: RecentSwapEvent[] }) {
  const mounted = useMounted();

  return (
    <section aria-labelledby="recent-activity-heading" className="max-w-5xl mx-auto px-5 pt-5 pb-3">
      <div className="border-t border-border pt-5">
        <h2 id="recent-activity-heading" className="font-sans font-semibold text-[15px] text-text-primary">
          Recent activity
        </h2>
        <p className="font-sans text-[12.5px] text-text-muted mt-1 mb-4 max-w-2xl">
          Unscored raw trades as observed. For risk context, see the hourly Live now view above.
        </p>

        {events.length === 0 ? (
          <div className="border border-border p-4">
            <p className="font-sans text-[13px] text-text-muted">
              No raw swap events observed yet. The live feed may be starting or temporarily quiet.
            </p>
          </div>
        ) : (
          <>
            <div className="border-t border-l border-border">
              {events.map((event) => (
                <div
                  key={`${event.tx_hash}-${event.log_index}`}
                  className="grid grid-cols-1 sm:grid-cols-[minmax(0,1.7fr)_minmax(100px,.65fr)_minmax(120px,.8fr)_auto] gap-2 sm:gap-4 items-baseline border-r border-b border-border px-3 py-2.5"
                >
                  <div className="min-w-0">
                    <div className="font-mono text-[11px] text-text-primary truncate">
                      {poolLabel(event)}
                    </div>
                    <div className="font-mono text-[10px] text-text-muted truncate">
                      {event.pair ?? "untracked pair"}
                    </div>
                  </div>
                  <div className="font-mono text-[11px] text-text-primary">
                    {event.implied_price == null ? "n/a" : event.implied_price.toFixed(6)}
                  </div>
                  <div className="font-mono text-[10px] text-text-muted" suppressHydrationWarning>
                    {mounted ? relativeTime(event.observed_at) : " "}
                  </div>
                  <div className="font-mono text-[10px] text-text-muted">
                    {sourceLabel[event.source]}
                  </div>
                </div>
              ))}
            </div>
            <p className="font-sans text-[11px] text-text-muted mt-3">
              Activity can be sparse because these pools do not trade continuously.
            </p>
          </>
        )}
      </div>
    </section>
  );
}