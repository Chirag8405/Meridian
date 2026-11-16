import type { EvaluationSummaryRow } from "@/lib/data";
import InfoTip from "./InfoTip";
import { ProcessTags } from "./Explain";

function Headline({
  label,
  big,
  line,
  tone,
}: {
  label: string;
  big: string;
  line: string;
  tone: "good" | "limit";
}) {
  return (
    <div className={`border bg-surface p-3 ${tone === "good" ? "border-text-primary" : "border-accent"}`}>
      <div className="font-mono text-[11px] text-text-muted">{label}</div>
      <div
        className={`font-mono text-[22px] font-medium leading-tight ${
          tone === "good" ? "text-text-primary" : "text-accent"
        }`}
      >
        {big}
      </div>
      <p className="font-sans text-[12.5px] leading-snug text-text-secondary mt-1">{line}</p>
    </div>
  );
}

export default function IntroExplainer({ evaluation }: { evaluation: EvaluationSummaryRow[] }) {
  const usdc = evaluation.find((r) => r.event_label === "USDC_MAR2023");
  const ust = evaluation.find((r) => r.event_label === "UST_MAY2022");

  return (
    <section id="intro" aria-labelledby="intro-heading" className="max-w-5xl mx-auto px-5 pt-4 pb-6 scroll-mt-4">
      <div className="border border-border bg-fill p-4 sm:p-5">
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <h2 id="intro-heading" className="font-sans font-semibold text-[15px] text-text-primary">
            What this project does
          </h2>
          <ProcessTags types={["batch", "streaming", "ml"]} />
          <InfoTip
            label="Where this page sits in the pipeline"
            info={{
              what: "The whole page mixes three kinds of result, and every section is tagged with one or more of them.",
              how: "Batch = Hadoop/Hive/Spark jobs on a frozen historical dataset. Streaming = the live Alchemy WebSocket feed processed by Spark Structured Streaming. ML model = a result produced by K-Means, logistic regression or a random forest.",
              read: "See the Architecture page for the full diagram.",
            }}
          />
        </div>
        <p className="font-sans text-[13.5px] leading-relaxed text-text-secondary max-w-3xl">
          A <strong className="text-text-primary font-semibold">stablecoin</strong> is a
          cryptocurrency designed to always be worth $1. Sometimes it isn&apos;t — a{" "}
          <strong className="text-text-primary font-semibold">depeg</strong>. By the time that
          shows up on a price chart, the damage is often already done. This page tracks how
          on-chain trading behavior — not price — looked in the run-up to two real depegs, and
          uses the same method to score current trading in real time below. Measured (not
          assumed) against USDC&apos;s 2023 depeg, this signal rose a full{" "}
          <strong className="text-text-primary font-semibold">3 days</strong> before price broke.
          Tested the same way against UST&apos;s 2022 collapse, it found no such lead time — UST
          was already unstable before this project&apos;s data even begins, a real limit stated
          plainly, not glossed over. See the methodology in{" "}
          <code className="font-mono text-[11.5px]">docs/FINDINGS.md</code>.
        </p>

        {usdc && ust && (
          <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 gap-3 max-w-3xl">
            <Headline
              tone="good"
              label="USDC · March 2023 (SVB exposure)"
              big={`${usdc.lead_time_hours} h lead time`}
              line={`The score first stayed elevated ${(usdc.lead_time_hours / 24).toFixed(0)} days before the price sustainably broke from $1. Price fell to $${usdc.min_price.toFixed(4)} and recovered.`}
            />
            <Headline
              tone="limit"
              label="UST · May 2022 (algorithmic collapse)"
              big={`${ust.lead_time_hours} h lead time`}
              line={`Not a missed warning: the score was already above the alarm level at the earliest data${ust.first_warning_ts ? ` (${new Date(ust.first_warning_ts).toLocaleDateString("en-US", { month: "long", day: "numeric", timeZone: "UTC" })})` : ""}, so there is no calm “before” to measure from.`}
            />
          </div>
        )}

        <p className="font-sans text-[12px] leading-relaxed text-text-muted mt-3 max-w-3xl">
          Every risk number on this page is on the same 0–100 scale: 0 is a normal, quiet
          market; higher means trading looks more like the historical crises this page is
          validated against. Look for the small bar under each score — it shows exactly where
          that reading falls on that scale. Click any{" "}
          <span
            aria-hidden="true"
            className="inline-flex h-4 w-4 items-center justify-center rounded-full border border-text-muted font-mono text-[10px] align-middle"
          >
            i
          </span>{" "}
          for what it means, how it is computed and which Big Data tool produced it.
        </p>
      </div>
    </section>
  );
}
