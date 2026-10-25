"use client";

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";
import type {
  ActivityFilters,
  ActivityWindow,
  RecentSwapActivity,
  RecentSwapEvent,
} from "@/lib/data";

const REFRESH_MS = 20_000;
const WINDOWS: ActivityWindow[] = ["15m", "1h", "6h", "24h"];
const DETAIL_ROWS = 12;
const STALE_MINUTES = 30;

const WIDTH = 640;
const HEIGHT = 180;
const PAD_LEFT = 32;
const PAD_RIGHT = 8;
const PAD_TOP = 12;
const PAD_BOTTOM = 24;

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

function clock(iso: string, withSeconds = false): string {
  return new Date(iso).toLocaleTimeString("en-GB", {
    timeZone: "UTC",
    hour: "2-digit",
    minute: "2-digit",
    second: withSeconds ? "2-digit" : undefined,
  });
}

function utcStamp(iso: string): string {
  return `${new Date(iso).toISOString().replace("T", " ").slice(0, 19)} UTC`;
}

function poolLabel(poolName: string): string {
  if (poolName === "curve_3pool") return "Curve 3pool";
  if (poolName === "uniswap_v2_usdc_usdt") return "Uniswap V2 · USDC/USDT";
  if (poolName === "uniswap_v2_usdc_dai") return "Uniswap V2 · USDC/DAI";
  return poolName;
}

const sourceLabel: Record<RecentSwapEvent["source"], string> = {
  alchemy_live: "live",
  alchemy_getlogs_replay: "gap-filled",
};

function buildQuery(
  filters: ActivityFilters,
  extra: Record<string, string> = {}
): string {
  const params = new URLSearchParams(extra);
  if (filters.pair) params.set("pair", filters.pair);
  if (filters.pool) params.set("pool", filters.pool);
  if (filters.source) params.set("source", filters.source);
  return params.toString();
}

function Select({
  label,
  value,
  options,
  format,
  onChange,
}: {
  label: string;
  value: string | null;
  options: string[];
  format?: (v: string) => string;
  onChange: (v: string | null) => void;
}) {
  return (
    <label className="flex items-center gap-1.5 font-mono text-[11px] text-text-muted">
      {label}
      <select
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value || null)}
        className="font-mono text-[11px] text-text-primary bg-surface border border-border px-1.5 py-1"
      >
        <option value="">all</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {format ? format(o) : o}
          </option>
        ))}
      </select>
    </label>
  );
}

function EventRow({ event }: { event: RecentSwapEvent }) {
  const [open, setOpen] = useState(false);
  const mounted = useMounted();
  const detail: [string, string][] = [
    ["Transaction hash", event.tx_hash],
    ["Log index", String(event.log_index)],
    ["Blockchain event time", utcStamp(event.event_ts)],
    ["Feed observed time", utcStamp(event.observed_at)],
    ["Pool address", event.pool_address],
    ["Price", event.implied_price == null ? "n/a" : event.implied_price.toFixed(6)],
  ];
  return (
    <div className="border-r border-b border-border">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="w-full text-left grid grid-cols-1 sm:grid-cols-[minmax(0,1.7fr)_minmax(100px,.65fr)_minmax(120px,.8fr)_auto] gap-2 sm:gap-4 items-baseline px-3 py-2.5 hover:bg-fill"
      >
        <div className="min-w-0">
          <div className="font-mono text-[11px] text-text-primary truncate">
            {poolLabel(event.pool_name)}
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
        <div className="font-mono text-[10px] text-text-muted">{sourceLabel[event.source]}</div>
      </button>
      {open && (
        <dl className="grid grid-cols-1 sm:grid-cols-[150px_minmax(0,1fr)] gap-x-4 gap-y-1 px-3 pb-3 font-mono text-[10.5px]">
          {detail.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-text-muted">{k}</dt>
              <dd className="text-text-primary break-all">{v}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  );
}

function ActivityGraph({
  activity,
  selected,
  onSelect,
}: {
  activity: RecentSwapActivity;
  selected: number | null;
  onSelect: (idx: number | null) => void;
}) {
  const { buckets } = activity;
  const [focusIdx, setFocusIdx] = useState<number | null>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  const plotW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotH = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const maxCount = Math.max(1, ...buckets.map((b) => b.total));
  const slot = plotW / buckets.length;
  const barW = Math.max(2, slot - 4);
  const barX = (i: number) => PAD_LEFT + i * slot + (slot - barW) / 2;
  const barH = (n: number) => (n / maxCount) * plotH;

  const active = focusIdx ?? selected;
  const activeBucket = active !== null ? buckets[active] : null;

  function indexFromPointer(e: React.PointerEvent<SVGRectElement>): number | null {
    const svg = svgRef.current;
    if (!svg) return null;
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * WIDTH;
    const idx = Math.floor((x - PAD_LEFT) / slot);
    return Math.max(0, Math.min(buckets.length - 1, idx));
  }

  function handleKeyDown(e: React.KeyboardEvent<SVGRectElement>) {
    const base = focusIdx ?? selected ?? 0;
    let next: number | null = null;
    if (e.key === "ArrowRight") next = Math.min(buckets.length - 1, base + 1);
    else if (e.key === "ArrowLeft") next = Math.max(0, base - 1);
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = buckets.length - 1;
    else if (e.key === "Escape") {
      onSelect(null);
      return;
    } else return;
    e.preventDefault();
    setFocusIdx(next);
    onSelect(next);
  }

  const tickEvery = Math.ceil(buckets.length / 6);

  return (
    <div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto select-none"
        role="img"
        aria-label={`Swaps observed per ${Math.round(activity.bucket_seconds / 60)} minutes, ${activity.summary.total} in the last ${activity.window}`}
      >
        {[0, 0.5, 1].map((f) => {
          const y = PAD_TOP + (1 - f) * plotH;
          return (
            <g key={f}>
              <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={y} y2={y} stroke="var(--border)" strokeWidth={1} />
              <text x={PAD_LEFT - 6} y={y + 4} textAnchor="end" className="font-mono fill-text-muted" fontSize={10}>
                {Math.round(maxCount * f)}
              </text>
            </g>
          );
        })}

        {buckets.map((b, i) => (
          <g key={b.start}>
            {/* Zero buckets still get a hairline so quiet periods stay visible. */}
            <rect
              x={barX(i)}
              y={PAD_TOP + plotH - Math.max(barH(b.total), 1)}
              width={barW}
              height={Math.max(barH(b.total), 1)}
              fill={b.total === 0 ? "var(--border)" : "var(--text-primary)"}
              opacity={selected !== null && selected !== i ? 0.35 : 1}
            />
            {active === i && (
              <rect
                x={PAD_LEFT + i * slot}
                y={PAD_TOP}
                width={slot}
                height={plotH}
                fill="none"
                stroke="var(--text-muted)"
                strokeWidth={1}
              />
            )}
            {i % tickEvery === 0 && (
              <text
                x={PAD_LEFT + i * slot + slot / 2}
                y={HEIGHT - 8}
                textAnchor="middle"
                className="font-mono fill-text-muted"
                fontSize={10}
              >
                {clock(b.start)}
              </text>
            )}
          </g>
        ))}

        <rect
          x={PAD_LEFT}
          y={PAD_TOP}
          width={plotW}
          height={plotH}
          fill="transparent"
          tabIndex={0}
          role="slider"
          aria-label="Select a time bucket"
          aria-valuemin={0}
          aria-valuemax={buckets.length - 1}
          aria-valuenow={active ?? 0}
          aria-valuetext={
            activeBucket
              ? `${clock(activeBucket.start)} to ${clock(activeBucket.end)} UTC: ${activeBucket.total} swaps`
              : undefined
          }
          onPointerMove={(e) => setFocusIdx(indexFromPointer(e))}
          onPointerLeave={() => setFocusIdx(null)}
          onClick={(e) => {
            const idx = indexFromPointer(e as unknown as React.PointerEvent<SVGRectElement>);
            if (idx !== null) onSelect(selected === idx ? null : idx);
          }}
          onKeyDown={handleKeyDown}
          onFocus={() => setFocusIdx((v) => v ?? selected ?? 0)}
          onBlur={() => setFocusIdx(null)}
          style={{ cursor: "pointer" }}
        />
      </svg>
      <div className="mt-1 min-h-5 font-mono text-[12px] text-text-secondary" aria-live="polite">
        {activeBucket ? (
          <span>
            {clock(activeBucket.start)}–{clock(activeBucket.end)} UTC ·{" "}
            <strong className="text-text-primary">{activeBucket.total}</strong> swap
            {activeBucket.total === 1 ? "" : "s"} ({activeBucket.live} live, {activeBucket.gap_filled} gap-filled)
          </span>
        ) : (
          <span className="text-text-muted">Click or focus a bar to inspect that interval</span>
        )}
      </div>
    </div>
  );
}

export default function RecentActivity({
  events: initialEvents,
  activity: initialActivity,
}: {
  events: RecentSwapEvent[];
  activity: RecentSwapActivity | null;
}) {
  const mounted = useMounted();
  const [windowSel, setWindowSel] = useState<ActivityWindow>("1h");
  const [filters, setFilters] = useState<ActivityFilters>({ pair: null, pool: null, source: null });
  const [selected, setSelected] = useState<number | null>(null);
  const [activity, setActivity] = useState<RecentSwapActivity | null>(initialActivity);
  const [events, setEvents] = useState<RecentSwapEvent[]>(initialEvents);
  const [error, setError] = useState(false);
  // The first render uses the server-fetched defaults; skip the redundant fetch.
  const isDefault = windowSel === "1h" && !filters.pair && !filters.pool && !filters.source;
  const skipFirst = useRef(true);
  const [tick, setTick] = useState(0);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    const id = setInterval(() => {
      setTick((t) => t + 1);
      setNow(Date.now());
    }, REFRESH_MS);
    return () => clearInterval(id);
  }, []);

  // Selection is index-based, so it only makes sense for the data that produced it.
  const changeWindow = (w: ActivityWindow) => {
    setWindowSel(w);
    setSelected(null);
  };
  const changeFilters = (patch: Partial<ActivityFilters>) => {
    setFilters((f) => ({ ...f, ...patch }));
    setSelected(null);
  };

  const bucket = selected !== null && activity ? activity.buckets[selected] : null;

  const load = useCallback(
    async (signal: AbortSignal) => {
      try {
        const eventExtra: Record<string, string> = { limit: String(DETAIL_ROWS) };
        if (bucket) {
          eventExtra.start = bucket.start;
          eventExtra.end = bucket.end;
        }
        const [actRes, evRes] = await Promise.all([
          fetch(`/api/recent-swap-activity?${buildQuery(filters, { window: windowSel })}`, { signal }),
          fetch(`/api/recent-swap-events?${buildQuery(filters, eventExtra)}`, { signal }),
        ]);
        // 404 = backend not yet redeployed with the new endpoints; keep the empty state.
        if (actRes.status === 404 || evRes.status === 404) return;
        if (!actRes.ok || !evRes.ok) throw new Error("fetch failed");
        setActivity(await actRes.json());
        setEvents(await evRes.json());
        setError(false);
      } catch (e) {
        if ((e as Error).name !== "AbortError") setError(true);
      }
    },
    [filters, windowSel, bucket]
  );

  useEffect(() => {
    if (skipFirst.current) {
      skipFirst.current = false;
      if (isDefault && selected === null) return;
    }
    const ctrl = new AbortController();
    void load(ctrl.signal);
    return () => ctrl.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- tick drives the 20s refresh
  }, [load, tick]);

  const lastObserved = activity?.summary.last_observed_at ?? null;
  const staleMinutes = lastObserved ? (now - new Date(lastObserved).getTime()) / 60000 : null;
  const isStale = mounted && staleMinutes !== null && staleMinutes > STALE_MINUTES;
  const hasFilter = Boolean(filters.pair || filters.pool || filters.source);

  return (
    <section aria-labelledby="recent-activity-heading" className="max-w-5xl mx-auto px-5 pt-5 pb-3">
      <div className="border-t border-border pt-5">
        <h2 id="recent-activity-heading" className="font-sans font-semibold text-[15px] text-text-primary">
          Recent activity
        </h2>
        <p className="font-sans text-[12.5px] text-text-muted mt-1 mb-4 max-w-2xl">
          Unscored raw trades as observed by the live feed. Counts are descriptive, not a risk
          signal. For risk context, see the hourly Live now view above.
        </p>

        {!activity ? (
          <div className="border border-border p-4">
            <p className="font-sans text-[13px] text-text-muted">
              No raw swap events observed yet. The live feed may be starting or temporarily quiet.
            </p>
          </div>
        ) : (
          <>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-3">
              <div role="group" aria-label="Time window" className="flex border border-border">
                {WINDOWS.map((w) => (
                  <button
                    key={w}
                    type="button"
                    aria-pressed={windowSel === w}
                    onClick={() => changeWindow(w)}
                    className={`font-mono text-[11px] px-2.5 py-1 ${
                      windowSel === w ? "bg-text-primary text-surface" : "text-text-primary hover:bg-fill"
                    }`}
                  >
                    {w}
                  </button>
                ))}
              </div>
              <Select
                label="pair"
                value={filters.pair}
                options={activity.filter_options.pairs}
                onChange={(pair) => changeFilters({ pair })}
              />
              <Select
                label="pool"
                value={filters.pool}
                options={activity.filter_options.pools}
                format={poolLabel}
                onChange={(pool) => changeFilters({ pool })}
              />
              <Select
                label="source"
                value={filters.source}
                options={activity.filter_options.sources}
                format={(v) => sourceLabel[v as RecentSwapEvent["source"]] ?? v}
                onChange={(source) => changeFilters({ source: source as ActivityFilters["source"] })}
              />
            </div>

            <dl className="grid grid-cols-2 sm:grid-cols-4 gap-px bg-border border border-border mb-4">
              {[
                [`Swaps in ${activity.window}`, String(activity.summary.total)],
                [
                  "Last observed",
                  lastObserved ? (mounted ? relativeTime(lastObserved) : " ") : "none retained",
                ],
                ["Active pools", String(activity.summary.active_pools)],
                ["Live / gap-filled", `${activity.summary.live} / ${activity.summary.gap_filled}`],
              ].map(([k, v]) => (
                <div key={k} className="bg-surface px-3 py-2">
                  <dt className="font-mono text-[10px] text-text-muted">{k}</dt>
                  <dd className="font-mono text-[13px] text-text-primary" suppressHydrationWarning>
                    {v}
                  </dd>
                </div>
              ))}
            </dl>

            {isStale && lastObserved && (
              <p className="font-sans text-[12px] text-text-muted mb-2">
                Latest observed event is {relativeTime(lastObserved)} — the feed may be quiet or paused.
              </p>
            )}
            {error && (
              <p className="font-sans text-[12px] text-text-muted mb-2">
                Couldn&apos;t refresh just now; showing the last loaded data.
              </p>
            )}

            <ActivityGraph activity={activity} selected={selected} onSelect={setSelected} />

            <p className="font-sans text-[11px] text-text-muted mt-2 mb-4">
              Bars bucket by when the feed observed each swap (UTC), not the on-chain timestamp.
              Only the latest {activity.retention.max_rows} events / {activity.retention.retention_hours} hours are
              retained
              {activity.retention.window_exceeds_retention
                ? ` — this ${activity.window} window reaches back further than that, so older bars are empty by retention, not necessarily by quiet trading.`
                : "."}
              {activity.summary.total > 0 && activity.summary.active_pools < 3
                ? " Pools trade intermittently, so gaps are normal."
                : ""}
            </p>

            <div className="flex items-baseline justify-between mb-2">
              <h3 className="font-sans font-semibold text-[13px] text-text-primary">
                {bucket
                  ? `Swaps ${clock(bucket.start)}–${clock(bucket.end)} UTC`
                  : `Latest swaps${hasFilter ? " (filtered)" : ""}`}
              </h3>
              {bucket && (
                <button
                  type="button"
                  onClick={() => setSelected(null)}
                  className="font-mono text-[11px] text-text-primary underline"
                >
                  Show all activity
                </button>
              )}
            </div>

            {events.length === 0 ? (
              <div className="border border-border p-4">
                <p className="font-sans text-[13px] text-text-muted">
                  No swaps observed in this window.
                </p>
              </div>
            ) : (
              <div className="border-t border-l border-border">
                {events.slice(0, DETAIL_ROWS).map((event) => (
                  <EventRow key={`${event.tx_hash}-${event.log_index}`} event={event} />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
