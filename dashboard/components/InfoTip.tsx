"use client";

import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import { INFO, type InfoContent, type InfoKey } from "@/lib/explain";

const ROWS: { key: keyof InfoContent; label: string }[] = [
  { key: "what", label: "What it means" },
  { key: "how", label: "How it is computed" },
  { key: "tech", label: "Big Data tool / technique" },
  { key: "read", label: "How to read it" },
];

/**
 * Small "i" button that opens an explanation popover.
 * Works on click / Enter / Space (not hover-only), closes on Esc, outside
 * click, or the close button, and returns focus to the button on Esc.
 * Pass either `k` (a key into lib/explain.ts) or inline `info`.
 */
export default function InfoTip({
  k,
  info,
  label,
}: {
  k?: InfoKey;
  info?: InfoContent;
  /** Short subject used in the button's accessible name. */
  label: string;
}) {
  const content: InfoContent | undefined = info ?? (k ? INFO[k] : undefined);
  const [open, setOpen] = useState(false);
  const [shift, setShift] = useState(0);
  const id = useId();
  const wrapRef = useRef<HTMLSpanElement>(null);
  const popRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        btnRef.current?.focus();
      }
    }
    function onPointer(e: PointerEvent) {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("keydown", onKey);
    document.addEventListener("pointerdown", onPointer);
    return () => {
      document.removeEventListener("keydown", onKey);
      document.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  // Keep the popover inside the viewport: measure after it opens and nudge it.
  useLayoutEffect(() => {
    if (!open || !popRef.current) return;
    const r = popRef.current.getBoundingClientRect();
    const vw = document.documentElement.clientWidth;
    const margin = 8;
    // Subtract the current shift so the measurement is stable across re-opens.
    const left = r.left - shift;
    const right = r.right - shift;
    let next = 0;
    if (right > vw - margin) next = vw - margin - right;
    if (left + next < margin) next = margin - left;
    if (next !== shift) setShift(next);
  }, [open, shift]);

  if (!content) return null;

  return (
    <span ref={wrapRef} className="relative inline-block align-middle">
      <button
        ref={btnRef}
        type="button"
        aria-label={`About: ${label}`}
        aria-expanded={open}
        aria-controls={open ? id : undefined}
        onClick={() => setOpen((v) => !v)}
        className="ml-1.5 inline-flex h-4 w-4 items-center justify-center rounded-full border border-text-muted text-text-muted font-mono text-[10px] leading-none hover:border-text-primary hover:text-text-primary"
      >
        i
      </button>
      {open && (
        <div
          ref={popRef}
          id={id}
          role="region"
          aria-label={`Explanation: ${label}`}
          style={{ transform: `translateX(${shift}px)` }}
          className="absolute left-0 top-full z-50 mt-1.5 w-[min(360px,calc(100vw-24px))] border border-border bg-surface p-3 text-left shadow-md"
        >
          <div className="mb-2 flex items-start justify-between gap-3">
            <span className="font-sans text-[12.5px] font-semibold text-text-primary">{label}</span>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                btnRef.current?.focus();
              }}
              aria-label="Close explanation"
              className="-mt-0.5 shrink-0 px-1 font-mono text-[13px] text-text-muted hover:text-text-primary"
            >
              ×
            </button>
          </div>
          <dl className="space-y-2">
            {ROWS.map(({ key, label: rowLabel }) =>
              content[key] ? (
                <div key={key}>
                  <dt className="font-sans text-[10px] font-semibold uppercase tracking-wide text-text-muted">
                    {rowLabel}
                  </dt>
                  <dd className="font-sans text-[12.5px] leading-snug font-normal normal-case text-text-secondary">
                    {content[key]}
                  </dd>
                </div>
              ) : null
            )}
          </dl>
          <p className="mt-2 font-sans text-[10.5px] text-text-muted">Esc to close</p>
        </div>
      )}
    </span>
  );
}
