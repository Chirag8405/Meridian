import Link from "next/link";
import { getEvaluationSummary, getMetadata } from "@/lib/data";
import EvaluationTable from "@/components/EvaluationTable";

export default async function EvaluationPage() {
  const rows = await getEvaluationSummary();
  const meta = await getMetadata();
  const usdc = rows.find((r) => r.event_label === "USDC_MAR2023");
  const ust = rows.find((r) => r.event_label === "UST_MAY2022");

  return (
    <main>
      <header className="max-w-5xl mx-auto px-5 pt-8 pb-2">
        <Link href="/" className="font-mono text-[12px] text-text-muted hover:text-text-primary">
          ← back to dashboard
        </Link>
        <h1 className="font-sans font-semibold text-[20px] tracking-tight text-text-primary mt-2">
          Evaluation
        </h1>
        <p className="font-sans text-[13px] text-text-muted mt-0.5 max-w-2xl">
          Does the risk score provide genuine early warning, or does it just relabel a crisis
          after it&apos;s already visible? Measured directly against real data, not assumed.
        </p>
      </header>

      <section className="max-w-5xl mx-auto px-5 pt-6 pb-4">
        <div className="border border-border bg-fill p-4 sm:p-5">
          <p className="font-sans text-[13px] leading-relaxed text-text-secondary">
            Method: an elevated threshold — calm-period mean + 2 standard deviations of{" "}
            <code className="font-mono text-[11.5px]">risk_score</code>, computed only from
            genuine calm (non-crisis) history — checked against an objective, price-based depeg
            onset, independent of the score itself. Both the warning signal and the depeg onset
            require a <strong className="text-text-primary font-medium">sustained</strong> (2+
            consecutive hours) crossing, not a single noisy hour — a real single-hour price
            spike in this data would otherwise have been mistaken for the depeg onset. Full
            methodology and the reasoning behind every choice:{" "}
            <code className="font-mono text-[11.5px]">docs/FINDINGS.md</code>.
          </p>
        </div>
      </section>

      <section className="max-w-5xl mx-auto px-5 pb-10">
        {!usdc || !ust ? (
          <div className="border border-border p-4 mt-4">
            <p className="font-sans text-[13px] text-text-muted">
              Evaluation data not available yet — this table is served the same way as the rest
              of the live dashboard and may not have been populated on every deployment.
            </p>
          </div>
        ) : (
          <EvaluationTable usdc={usdc} ust={ust} />
        )}
      </section>

      <footer className="max-w-5xl mx-auto px-5 py-6 border-t border-border">
        <p className="font-mono text-[11px] text-text-muted">
          Data exported {new Date(meta.exported_at).toLocaleString("en-US", {
            dateStyle: "medium",
            timeStyle: "short",
          })}
          . Computed in <code className="font-mono">spark/evaluation_summary.scala</code>, see
          project docs/FINDINGS.md and docs/ARCHITECTURE.md.
        </p>
      </footer>
    </main>
  );
}
