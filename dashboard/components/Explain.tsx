import type { ReactNode } from "react";

export type ProcessType = "batch" | "streaming" | "ml";

// Monochrome + the site's red accent only. Each type is also distinguishable
// without colour: outline, red outline (live), dashed outline.
const META: Record<ProcessType, { label: string; glyph: string; cls: string; title: string }> = {
  batch: {
    label: "Batch · Hadoop/Hive/Spark",
    glyph: "▪",
    cls: "border-text-primary text-text-primary",
    title: "Computed offline by Spark/Hive jobs on frozen historical data, then exported",
  },
  streaming: {
    label: "Streaming · WebSocket",
    glyph: "●",
    cls: "border-accent text-accent",
    title: "Fed continuously by the Alchemy WebSocket live feed",
  },
  ml: {
    label: "ML model",
    glyph: "◆",
    cls: "border-dashed border-text-muted text-text-secondary",
    title: "Produced by a trained or fitted model (K-Means, logistic regression, random forest)",
  },
};

/** Tag showing where a section sits in the pipeline. */
export function ProcessTag({ type }: { type: ProcessType }) {
  const m = META[type];
  return (
    <span
      title={m.title}
      className={`inline-flex items-center gap-1 whitespace-nowrap border px-1.5 py-0.5 font-sans text-[11px] font-medium leading-none ${m.cls}`}
    >
      <span aria-hidden="true" className="text-[9px]">
        {m.glyph}
      </span>
      {m.label}
    </span>
  );
}

export function ProcessTags({ types }: { types: ProcessType[] }) {
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      {types.map((t) => (
        <ProcessTag key={t} type={t} />
      ))}
    </span>
  );
}

/** One-line "What am I looking at?" caption under a heading, chart or table. */
export function WhatIsThis({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <p className={`font-sans text-[13px] leading-relaxed text-text-muted max-w-2xl ${className}`}>
      <span className="font-medium text-text-secondary">What am I looking at? </span>
      {children}
    </p>
  );
}

/** "How to read this" line for charts: axes, units, legends. */
export function HowToRead({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <p className={`font-sans text-[12.5px] leading-relaxed text-text-muted max-w-2xl ${className}`}>
      <span className="font-medium text-text-secondary">How to read it: </span>
      {children}
    </p>
  );
}
