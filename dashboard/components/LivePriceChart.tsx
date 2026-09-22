"use client";

import { useState } from "react";
import type { LivePricePoint } from "@/lib/data";

const WIDTH = 640;
const HEIGHT = 200;
const PAD_LEFT = 52;
const PAD_RIGHT = 12;
const PAD_TOP = 16;
const PAD_BOTTOM = 24;

function formatTime(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatPrice(v: number) {
  return `$${v.toFixed(4)}`;
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

export default function LivePriceChart({ pair, series }: { pair: string; series: Series[] }) {
  const [hoverX, setHoverX] = useState<number | null>(null);

  const allPoints = series.flatMap((s) => s.points);
  if (allPoints.length === 0) {
    return (
      <div className="flex-1 min-w-0">
        <h3 className="font-sans font-semibold text-[15px] text-text-primary mb-1">{pair}</h3>
        <div className="border border-border p-4 h-[120px] flex items-center">
          <p className="font-sans text-[12.5px] text-text-muted">
            No finalized hourly window yet for this pair — the streaming consumer emits one
            roughly every 10 minutes once enough live data has arrived. Check back shortly.
          </p>
        </div>
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
      <div className="flex items-baseline justify-between mb-1">
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
            <text x={PAD_LEFT - 6} y={yAt(v) + 3} textAnchor="end" className="font-mono fill-text-muted" fontSize={10}>
              {formatPrice(v)}
            </text>
          </g>
        ))}

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
      <div className="mt-1 h-5 font-mono text-[11px] text-text-secondary" aria-live="polite">
        {hoverReadouts && hoverReadouts.length > 0 ? (
          <span>
            {hoverReadouts.map((r, i) => (
              <span key={r.label}>
                {i > 0 && "  ·  "}
                {r.label} <strong className="text-text-primary">{formatPrice(r.point.implied_price)}</strong>
                {" "}({formatTime(r.point.window_start_ts)})
              </span>
            ))}
          </span>
        ) : (
          <span className="text-text-muted">
            {allPoints.length} reading{allPoints.length === 1 ? "" : "s"} · hover or focus the chart to read a value
          </span>
        )}
      </div>
    </div>
  );
}
