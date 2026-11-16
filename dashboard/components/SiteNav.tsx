"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

type Step = { href: string; title: string; say: string };

// Walkthrough order for the presenter. Talking points restate what is on the
// screen and in docs/FINDINGS.md; no new claims.
const STEPS: Step[] = [
  {
    href: "/#intro",
    title: "1 · The problem and the headline",
    say: "A stablecoin should stay at $1. Measured against USDC's 2023 depeg the score rose 3 days early; for UST it found no lead time, and the page says why.",
  },
  {
    href: "/architecture",
    title: "2 · Architecture",
    say: "Dune and an Alchemy WebSocket feed HDFS/Hive. Spark computes statistics, K-Means, PageRank, the classifier and the score. The batch path is frozen history; the streaming path scores live swaps with the same frozen model.",
  },
  {
    href: "/#live-heading",
    title: "3 · Live now",
    say: "Live risk scores per pool, scored by Spark Structured Streaming. Point out the 0–100 bar, the crisis marker and the live / gap-filled badge.",
  },
  {
    href: "/#recent-activity-heading",
    title: "4 · Recent activity",
    say: "Raw swaps the live feed observed. Counts are descriptive only. Use the window buttons and click a bar to inspect one interval.",
  },
  {
    href: "/#risk-heading",
    title: "5 · Risk score per pair",
    say: "Four signals combine into one score. UST pairs show \"no reliable baseline\" because UST was already unstable before the data starts.",
  },
  {
    href: "/#crisis-heading",
    title: "6 · USDC recovered. UST didn't.",
    say: "Two real depegs on the same $0–$1.05 axis. USDC bottomed at $0.8808 and came back; UST fell to $0.0334.",
  },
  {
    href: "/#classifier-heading",
    title: "7 · Classifier",
    say: "Train on one coin, test on the other. It beat the rule-based baseline on UST and lost on USDC. Both results are reported.",
  },
  {
    href: "/#wallet-heading",
    title: "8 · Wallet PageRank",
    say: "Most top-ranked addresses are routers and aggregators, verified with an on-chain bytecode check, not traders.",
  },
  {
    href: "/evaluation",
    title: "9 · Evaluation",
    say: "The key result: 72 h lead time for USDC with 12 false alarms; 0 h for UST because its data starts already elevated.",
  },
  {
    href: "/#live-vs-frozen",
    title: "10 · What's live and what isn't",
    say: "Only \"Live now\" and \"Recent activity\" are live. The crisis charts, classifier and wallet rankings are a frozen dataset.",
  },
];

type Page = "home" | "architecture" | "evaluation";

const LINKS: { href: string; label: string; key: Page | "glossary" }[] = [
  { href: "/architecture", label: "Architecture", key: "architecture" },
  { href: "/evaluation", label: "Evaluation", key: "evaluation" },
  { href: "/#glossary", label: "Glossary", key: "glossary" },
];

// Same look as the original header's "Evaluation →" button.
const BTN =
  "font-sans text-[12px] font-medium px-2.5 py-1 border border-text-primary text-text-primary hover:bg-fill shrink-0";

/** Header buttons (placed inside each page's existing header row) + demo guide drawer. */
export default function SiteNav({ current }: { current: Page }) {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") {
        setOpen(false);
        btnRef.current?.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  return (
    <>
      <nav aria-label="Site" className="flex flex-wrap items-center gap-1.5">
        {current !== "home" && (
          <Link href="/" className={BTN}>
            ← Dashboard
          </Link>
        )}
        {LINKS.filter((l) => l.key !== current).map((l) => (
          <Link key={l.key} href={l.href} className={BTN}>
            {l.label}
          </Link>
        ))}
        <button
          ref={btnRef}
          type="button"
          aria-expanded={open}
          aria-controls="demo-guide"
          onClick={() => setOpen((v) => !v)}
          className={`${BTN} ${open ? "bg-text-primary text-surface hover:bg-text-primary" : ""}`}
        >
          Demo guide
        </button>
      </nav>

      {open && (
        <aside
          id="demo-guide"
          aria-label="Demo guide"
          className="fixed right-0 top-0 z-40 h-full w-[min(360px,100vw)] overflow-y-auto border-l border-border bg-surface p-5 shadow-md"
        >
          <div className="flex items-start justify-between gap-3 mb-1">
            <h2 className="font-sans text-[15px] font-semibold text-text-primary">Demo guide</h2>
            <button
              type="button"
              onClick={() => {
                setOpen(false);
                btnRef.current?.focus();
              }}
              aria-label="Close demo guide"
              className="px-1 font-mono text-[15px] leading-none text-text-muted hover:text-text-primary"
            >
              ×
            </button>
          </div>
          <p className="font-sans text-[12.5px] text-text-muted mb-4">
            Suggested order. Click a step to jump to it. Press Esc to close.
          </p>
          <ol className="space-y-3">
            {STEPS.map((s) => (
              <li key={s.href} className="border-t border-border pt-3">
                <Link
                  href={s.href}
                  className="font-sans text-[13px] font-semibold text-text-primary underline decoration-border underline-offset-4 hover:decoration-text-primary"
                >
                  {s.title}
                </Link>
                <p className="font-sans text-[12.5px] leading-snug text-text-muted mt-1">{s.say}</p>
              </li>
            ))}
          </ol>
        </aside>
      )}
    </>
  );
}
