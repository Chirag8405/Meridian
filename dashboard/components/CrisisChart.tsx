"use client";

import { useEffect, useRef, useState } from "react";
import type { TimelinePoint } from "@/lib/data";

const WIDTH = 640;
const HEIGHT = 260;
const PAD_LEFT = 44;
const PAD_RIGHT = 12;
const PAD_TOP = 16;
const PAD_BOTTOM = 28;
const Y_MAX = 1.05; // shared domain across both charts — the point of this component

function formatDate(iso: string) {
  const d = new Date(iso);
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatPrice(v: number) {
  return `$${v.toFixed(4)}`;
}

// Direct labels on a dense, noisy line need a backing plate — otherwise the
// line itself crosses through the text and the label goes illegible.
function LabelWithPlate({
  x,
  y,
  text,
  anchor,
  weight,
  aboveIfRoom,
}: {
  x: number;
  y: number;
  text: string;
  anchor: "start" | "middle" | "end";
  weight: number;
  aboveIfRoom: boolean;
}) {
  const dy = aboveIfRoom ? -12 : 16;
  const labelY = y + dy;
  const charWidth = 6.2;
  const plateW = text.length * charWidth + 8;
  const plateX = anchor === "end" ? x - plateW + 2 : anchor === "middle" ? x - plateW / 2 : x - 4;
  return (
    <g>
      <rect
        x={plateX}
        y={labelY - 11}
        width={plateW}
        height={14}
        fill="var(--surface)"
        opacity={0.92}
      />
      <text x={x} y={labelY} textAnchor={anchor} className="font-mono fill-text-primary" fontSize={11} fontWeight={weight}>
        {text}
      </text>
    </g>
  );
}

export default function CrisisChart({
  title,
  dateRangeLabel,
  points,
}: {
  title: string;
  dateRangeLabel: string;
  points: TimelinePoint[];
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [pathLength, setPathLength] = useState<number | null>(null);
  const [revealed, setRevealed] = useState(false);
  const svgRef = useRef<SVGSVGElement>(null);
  const pathRef = useRef<SVGPathElement>(null);

  const plotW = WIDTH - PAD_LEFT - PAD_RIGHT;
  const plotH = HEIGHT - PAD_TOP - PAD_BOTTOM;

  const xAt = (i: number) => PAD_LEFT + (i / (points.length - 1)) * plotW;
  const yAt = (price: number) => PAD_TOP + (1 - price / Y_MAX) * plotH;

  // Plain computation, not memoized: points is static per chart instance
  // (server-rendered once, never changes across this component's life), and
  // the map over ~200 points is cheap enough that useMemo's bookkeeping
  // isn't worth it — it was also pulling xAt/yAt into a stale-dependency
  // lint warning for no real benefit.
  const pathD = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${xAt(i).toFixed(2)},${yAt(p.implied_price).toFixed(2)}`)
    .join(" ");

  let lowIdx = 0;
  for (let i = 1; i < points.length; i++) {
    if (points[i].implied_price < points[lowIdx].implied_price) lowIdx = i;
  }

  // Fully declarative draw-in: measure the path once on mount, then flip a
  // state flag next frame so React's own re-render animates dashoffset -> 0
  // (see the style prop on the <path> below). Reduced-motion skips straight
  // to the final visible state. `revealed` already starts false, so the
  // effect only ever moves it forward — no synchronous reset needed.
  useEffect(() => {
    const el = pathRef.current;
    if (!el) return;
    setPathLength(el.getTotalLength());
    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setRevealed(true);
      return;
    }
    const raf = requestAnimationFrame(() => setRevealed(true));
    return () => cancelAnimationFrame(raf);
  }, [pathD]);

  function handlePointerMove(e: React.PointerEvent<SVGRectElement>) {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width) * WIDTH;
    const frac = (x - PAD_LEFT) / plotW;
    const idx = Math.round(frac * (points.length - 1));
    setHoverIdx(Math.max(0, Math.min(points.length - 1, idx)));
  }

  function handleKeyDown(e: React.KeyboardEvent<SVGRectElement>) {
    setHoverIdx((cur) => {
      const base = cur ?? 0;
      if (e.key === "ArrowRight") return Math.min(points.length - 1, base + 1);
      if (e.key === "ArrowLeft") return Math.max(0, base - 1);
      if (e.key === "Home") return 0;
      if (e.key === "End") return points.length - 1;
      return cur;
    });
  }

  const active = hoverIdx !== null ? points[hoverIdx] : null;
  const startP = points[0];
  const endP = points[points.length - 1];
  const lowP = points[lowIdx];

  return (
    <div className="flex-1 min-w-0">
      <h3 className="font-sans font-semibold text-[15px] text-text-primary mb-0.5">{title}</h3>
      <p className="font-mono text-[12px] text-text-muted mb-3">{dateRangeLabel}</p>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        className="w-full h-auto select-none"
        role="img"
        aria-label={`${title}: price from ${formatPrice(startP.implied_price)} to ${formatPrice(
          endP.implied_price
        )}, low of ${formatPrice(lowP.implied_price)}`}
      >
        {/* Y gridlines + peg reference at $1.00 */}
        {[0, 0.25, 0.5, 0.75, 1.0].map((v) => (
          <g key={v}>
            <line
              x1={PAD_LEFT}
              x2={WIDTH - PAD_RIGHT}
              y1={yAt(v)}
              y2={yAt(v)}
              stroke="var(--border)"
              strokeWidth={v === 1.0 ? 1.25 : 1}
              strokeDasharray={v === 1.0 ? "3 3" : undefined}
            />
            <text
              x={PAD_LEFT - 8}
              y={yAt(v) + 4}
              textAnchor="end"
              className="font-mono fill-text-muted"
              fontSize={11}
            >
              ${v.toFixed(2)}
            </text>
          </g>
        ))}

        {/* Price line — drawn in once on mount (declarative dasharray/offset
            driven entirely by React state, see the effect above), then
            static. Before pathLength is measured, render fully solid so
            there's no flash of an invisible line. */}
        <path
          ref={pathRef}
          d={pathD}
          fill="none"
          stroke="var(--text-primary)"
          strokeWidth={2}
          strokeLinejoin="round"
          strokeLinecap="round"
          style={
            pathLength === null
              ? undefined
              : {
                  strokeDasharray: pathLength,
                  strokeDashoffset: revealed ? 0 : pathLength,
                  transition: "stroke-dashoffset 1.1s ease-out",
                }
          }
        />

        {/* Direct labels: start, low, end */}
        <g>
          <circle cx={xAt(0)} cy={yAt(startP.implied_price)} r={3} fill="var(--text-primary)" stroke="var(--surface)" strokeWidth={2} />
          <circle cx={xAt(lowIdx)} cy={yAt(lowP.implied_price)} r={3} fill="var(--text-primary)" stroke="var(--surface)" strokeWidth={2} />
          <circle
            cx={xAt(points.length - 1)}
            cy={yAt(endP.implied_price)}
            r={3}
            fill="var(--text-primary)"
            stroke="var(--surface)"
            strokeWidth={2}
          />
          <LabelWithPlate
            x={xAt(lowIdx)}
            y={yAt(lowP.implied_price)}
            text={`low ${formatPrice(lowP.implied_price)}`}
            anchor="middle"
            weight={600}
            aboveIfRoom={yAt(lowP.implied_price) > PAD_TOP + 24}
          />
          <LabelWithPlate
            x={xAt(points.length - 1)}
            y={yAt(endP.implied_price)}
            text={formatPrice(endP.implied_price)}
            anchor="end"
            weight={400}
            aboveIfRoom={yAt(endP.implied_price) > PAD_TOP + 24}
          />
        </g>

        {/* Crosshair + hover hit layer */}
        {active && (
          <line
            x1={xAt(hoverIdx!)}
            x2={xAt(hoverIdx!)}
            y1={PAD_TOP}
            y2={HEIGHT - PAD_BOTTOM}
            stroke="var(--text-muted)"
            strokeWidth={1}
          />
        )}
        <rect
          x={PAD_LEFT}
          y={PAD_TOP}
          width={plotW}
          height={plotH}
          fill="transparent"
          tabIndex={0}
          role="slider"
          aria-label="Scrub timeline"
          aria-valuemin={0}
          aria-valuemax={points.length - 1}
          aria-valuenow={hoverIdx ?? 0}
          aria-valuetext={active ? `${formatDate(active.window_start_ts)}: ${formatPrice(active.implied_price)}` : undefined}
          onPointerMove={handlePointerMove}
          onPointerLeave={() => setHoverIdx(null)}
          onKeyDown={handleKeyDown}
          onFocus={() => setHoverIdx((v) => v ?? 0)}
          style={{ cursor: "crosshair" }}
        />
      </svg>

      {/* Tooltip / readout — same info on hover and keyboard focus */}
      <div className="mt-2 h-6 font-mono text-[12px] text-text-secondary" aria-live="polite">
        {active ? (
          <span>
            {formatDate(active.window_start_ts)} · <strong className="text-text-primary">{formatPrice(active.implied_price)}</strong>
            {"  "}· volume ${Math.round(active.volume_usd).toLocaleString()}
          </span>
        ) : (
          <span className="text-text-muted">Hover or focus the chart to read a value</span>
        )}
      </div>
    </div>
  );
}
