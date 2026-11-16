"use client";

import { useId, useState } from "react";
import type { LivePricePoint } from "@/lib/data";
import InfoTip from "./InfoTip";

// ViewBox is close to the rendered column width (~470px) so SVG text renders
// near its nominal size instead of being scaled down.
const WIDTH = 640;
const HEIGHT = 246;
const PAD_LEFT = 64;
const PAD_RIGHT = 12;
const PAD_TOP = 16;
const PAD_BOTTOM = 46;

// A reading backed by less than this much traded value is "dust": its implied
// price is a ratio of two tiny amounts, not a market price. This is a
// display filter only; the data is never modified.
const DUST_USD = 1;
// Distance from $1.00 beyond which a reading is called out in the note below.
const OUTLIER_DEV = 0.05;

function formatTime(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatDay(ms: number) {
  return new Date(ms).toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatPrice(v: number) {
  return `$${v.toFixed(4)}`;
}

function formatVolume(v: number) {
  return v < 0.01 ? v.toExponential(1) : v.toFixed(2);
}

// Nearest point in time to a hovered instant, within a series — undefined
// if the series has no points close enough to be a meaningful match (more
// than one full series' time-span away), so a very sparse series doesn't
// claim a misleadingly distant point as "the" value at the hovered time.
function nearestInTime(points: LivePricePoint[], targetMs: number): LivePricePoint | undefined {
  if (points.length === 0) return undefined;
  let best = points[0];
  let bestDiff = Math.abs(new Date(best.window_start_ts).getTime() - targetMs);
  for (const p of points) {
    const diff = Math.abs(new Date(p.window_start_ts).getTime() - targetMs);
    if (diff < bestDiff) {
      best = p;
      bestDiff = diff;
    }
  }
  return best;
}

type Series = { label: string; dash: boolean; points: LivePricePoint[] };

export default function LivePriceChart({ pair, series: fullSeries }: { pair: string; series: Series[] }) {
  const [hoverX, setHoverX] = useState<number | null>(null);
  const [hideDust, setHideDust] = useState(false);
  const toggleId = useId();

  const fullPoints = fullSeries.flatMap((s) => s.points);
  const dustPoints = fullPoints.filter((p) => p.volume_usd < DUST_USD);
  const outliers = fullPoints.filter((p) => Math.abs(p.implied_price - 1) > OUTLIER_DEV);
  const outliersAllDust = outliers.length > 0 && outliers.every((p) => p.volume_usd < DUST_USD);
  const worst = outliers.reduce<LivePricePoint | null>(
    (w, p) => (w === null || Math.abs(p.implied_price - 1) > Math.abs(w.implied_price - 1) ? p : w),
    null
  );

  const series: Series[] = hideDust
    ? fullSeries.map((s) => ({ ...s, points: s.points.filter((p) => p.volume_usd >= DUST_USD) }))
    : fullSeries;
  const allPoints = series.flatMap((s) => s.points);

  if (allPoints.length === 0) {
    return (
      <div className="flex-1 min-w-0">
        <h3 className="font-sans font-semibold text-[15px] text-text-primary mb-1">{pair}</h3>
        <div className="border border-border p-4 min-h-[120px] flex items-center">
          <p className="font-sans text-[12.5px] text-text-muted">
            {hideDust
              ? "Every hour in this chart is a dust hour, so nothing is left to draw. Untick the filter to see them."
              : "No finalized hourly window yet for this pair — the streaming consumer emits one roughly every 10 minutes once enough live data has arrived. Check back shortly."}
          </p>
        </div>
        {hideDust && (
          <label className="mt-2 flex cursor-pointer items-center gap-2 font-sans text-[12px] text-text-secondary">
            <input
              type="checkbox"
              checked={hideDust}
              onChange={(e) => setHideDust(e.target.checked)}
              className="h-4 w-4"
            />
            Hide dust hours (under ${DUST_USD} traded)
          </label>
        )}
      </div>
    );
  }

  // Auto-scaled Y axis, not a fixed $0-$1.05 domain like the historical
  // crisis charts — live prices sit tightly around $1 in calm conditions,
  // and a fixed wide domain would flatten any real movement into an
  // invisible near-straight line. A small pad keeps a flat/near-flat
  // series from looking like it's touching the plot edges.
  const prices = allPoints.map((p) => p.implied_price);
  const rawMin = Math.min(...prices, 1.0);
  const rawMax = Math.max(...prices, 1.0);
  const span = Math.max(rawMax - rawMin, 0.002);
  const yMin = rawMin - span * 0.25;
  const yMax = rawMax + span * 0.25;

  const allTimes = allPoints.map((p) => new Date(p.window_start_ts).getTime());
  const tMin = Math.min(...allTimes);
  const tMax = Math.max(...allTimes);
  const tSpan = Math.max(tMax - tMin, 1);

  const plotW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotH = HEIGHT - PAD_TOP - PAD_BOTTOM;
  const xAt = (iso: string) => PAD_LEFT + ((new Date(iso).getTime() - tMin) / tSpan) * plotW;
  const yAt = (price: number) => PAD_TOP + (1 - (price - yMin) / (yMax - yMin)) * plotH;
  const timeAtX = (x: number) => tMin + ((x - PAD_LEFT) / plotW) * tSpan;

  const yTicks = [yMin, (yMin + yMax) / 2, yMax];
  const xTicks = [tMin, tMin + tSpan / 2, tMax];

  function handlePointerMove(e: React.PointerEvent<SVGRectElement>) {
    const svg = e.currentTarget.ownerSVGElement;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * WIDTH;
    setHoverX(Math.max(PAD_LEFT, Math.min(WIDTH - PAD_RIGHT, x)));
  }

  const hoverReadouts =
    hoverX === null
      ? null
      : series
          .map((s) => ({ label: s.label, point: nearestInTime(s.points, timeAtX(hoverX)) }))
          .filter((r): r is { label: string; point: LivePricePoint } => r.point !== undefined);

  return (
    <div className="flex-1 min-w-0">
      <div className="flex flex-wrap items-baseline justify-between gap-y-1 mb-1">
        <h3 className="font-sans font-semibold text-[15px] text-text-primary">{pair}</h3>
        <div className="flex gap-3">
          {series.map((s) => (
            <span key={s.label} className="flex items-center gap-1.5 font-mono text-[10.5px] text-text-muted">
              <svg width="14" height="2" aria-hidden="true">
                <line
                  x1={0} y1={1} x2={14} y2={1}
                  stroke="var(--text-primary)" strokeWidth={1.5}
                  strokeDasharray={s.dash ? "3 2" : undefined}
                />
              </svg>
              {s.label}
            </span>
          ))}
        </div>
      </div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full h-auto select-none" role="img"
        aria-label={`${pair} live implied price, ${allPoints.length} reading(s)`}>
        {yTicks.map((v, i) => (
          <g key={i}>
            <line x1={PAD_LEFT} x2={WIDTH - PAD_RIGHT} y1={yAt(v)} y2={yAt(v)} stroke="var(--border)" strokeWidth={1} />
            <text x={PAD_LEFT - 6} y={yAt(v) + 4} textAnchor="end" className="font-mono fill-text-muted" fontSize={10}>
              {formatPrice(v)}
            </text>
          </g>
        ))}

        {/* Axis titles and time ticks */}
        <text
          transform={`translate(11 ${PAD_TOP + plotH / 2}) rotate(-90)`}
          textAnchor="middle"
          className="font-sans fill-text-muted"
          fontSize={10}
        >
          implied price ($)
        </text>
        {xTicks.map((t, i) => (
          <text
            key={i}
            x={PAD_LEFT + ((t - tMin) / tSpan) * plotW}
            y={HEIGHT - PAD_BOTTOM + 16}
            textAnchor={i === 0 ? "start" : i === xTicks.length - 1 ? "end" : "middle"}
            className="font-mono fill-text-muted"
            fontSize={10}
          >
            {formatDay(t)}
          </text>
        ))}
        <text
          x={PAD_LEFT + plotW / 2}
          y={HEIGHT - 6}
          textAnchor="middle"
          className="font-sans fill-text-muted"
          fontSize={10}
        >
          time (hourly windows, your local date)
        </text>

        {series.map((s) => {
          if (s.points.length === 0) return null;
          if (s.points.length === 1) {
            const p = s.points[0];
            return (
              <circle
                key={s.label}
                cx={xAt(p.window_start_ts)} cy={yAt(p.implied_price)}
                r={3} fill="var(--text-primary)" stroke="var(--surface)" strokeWidth={1.5}
              />
            );
          }
          const d = s.points
            .map((p, i) => `${i === 0 ? "M" : "L"}${xAt(p.window_start_ts).toFixed(2)},${yAt(p.implied_price).toFixed(2)}`)
            .join(" ");
          return (
            <g key={s.label}>
              <path d={d} fill="none" stroke="var(--text-primary)" strokeWidth={1.75}
                strokeDasharray={s.dash ? "4 3" : undefined} strokeLinejoin="round" strokeLinecap="round" />
            </g>
          );
        })}

        {hoverReadouts && hoverReadouts.length > 0 && (
          <>
            <line x1={hoverX!} x2={hoverX!} y1={PAD_TOP} y2={HEIGHT - PAD_BOTTOM} stroke="var(--text-muted)" strokeWidth={1} />
            {hoverReadouts.map((r) => (
              <circle
                key={r.label}
                cx={xAt(r.point.window_start_ts)} cy={yAt(r.point.implied_price)}
                r={3.5} fill="var(--text-primary)" stroke="var(--surface)" strokeWidth={1.5}
              />
            ))}
          </>
        )}

        {/* Full-width hover strip, same forgiving interaction model as
            CrisisChart — snaps to whichever point in each series is
            nearest in time to the cursor, rather than requiring a precise
            hit on a small per-point target. */}
        <rect
          x={PAD_LEFT} y={PAD_TOP} width={plotW} height={plotH}
          fill="transparent" tabIndex={0} role="slider"
          aria-label={`Scrub ${pair} live price`}
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHoverX(null)}
          onFocus={() => setHoverX((x) => x ?? PAD_LEFT + plotW)}
          style={{ cursor: "crosshair" }}
        />
      </svg>
      <div className="mt-1 min-h-5 font-mono text-[11px] text-text-secondary" aria-live="polite">
        {hoverReadouts && hoverReadouts.length > 0 ? (
          <span>
            {hoverReadouts.map((r, i) => (
              <span key={r.label}>
                {i > 0 && "  ·  "}
                {r.label} <strong className="text-text-primary">{formatPrice(r.point.implied_price)}</strong>
                {" "}({formatTime(r.point.window_start_ts)}, ${formatVolume(r.point.volume_usd)} traded)
              </span>
            ))}
          </span>
        ) : (
          <span className="text-text-muted">
            {allPoints.length} reading{allPoints.length === 1 ? "" : "s"} · hover or focus the chart to read a value
          </span>
        )}
      </div>

      {dustPoints.length > 0 && (
        <div className="mt-2 flex flex-wrap items-center gap-x-1 gap-y-1">
          <label htmlFor={toggleId} className="flex cursor-pointer items-center gap-2 font-sans text-[12px] text-text-secondary">
            <input
              id={toggleId}
              type="checkbox"
              checked={hideDust}
              onChange={(e) => setHideDust(e.target.checked)}
              className="h-4 w-4"
            />
            Hide dust hours (under ${DUST_USD} traded)
          </label>
          <InfoTip k="dustToggle" label="Hide dust hours" />
          <span className="font-mono text-[10.5px] text-text-muted">
            {hideDust
              ? `${dustPoints.length} of ${fullPoints.length} hours hidden`
              : `${dustPoints.length} of ${fullPoints.length} hours are dust`}
          </span>
        </div>
      )}

      {outliers.length > 0 && worst && (
        <aside aria-label={`Why is there a spike in ${pair}?`} className="mt-2 border border-border border-l-2 border-l-accent bg-fill p-3">
          <p className="font-sans text-[12.5px] font-semibold text-text-primary">Why is there a spike?</p>
          <p className="font-sans text-[12px] leading-relaxed text-text-muted mt-1">
            {outliers.length} reading{outliers.length === 1 ? "" : "s"} here sit more than 5% away from $1.00 (the
            furthest is {formatPrice(worst.implied_price)}, in an hour with only ${formatVolume(worst.volume_usd)}{" "}
            traded).
            {outliersAllDust
              ? " Every one of them is a dust hour: less than $1 changed hands."
              : " Not all of them are dust hours, so check the volume before reading them as a depeg."}{" "}
            A swap&apos;s price is the ratio of the two token amounts, and for a tiny trade that ratio is jumpy and
            says nothing about the market. The hourly price is the plain average of swap prices, not weighted by
            size, and the pipeline only flags zero or undefined prices, so one dust swap in a thin hour moves the
            line. docs/FINDINGS.md calls this kind of print a &ldquo;thin-trade artifact&rdquo;. Nothing has been
            removed from the data; use the checkbox above to hide dust hours.
          </p>
        </aside>
      )}
    </div>
  );
}
