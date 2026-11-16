import type { ClassifierMetricRow } from "@/lib/data";
import InfoTip from "./InfoTip";
import { HowToRead, ProcessTags, WhatIsThis } from "./Explain";

const SCORER_LABEL: Record<string, string> = {
  logistic_regression: "Logistic regression",
  random_forest: "Random forest",
  rule_based_baseline: "Rule-based baseline",
};

function DirectionPanel({
  title,
  description,
  verdict,
  rows,
}: {
  title: string;
  description: string;
  verdict: "beats" | "loses";
  rows: ClassifierMetricRow[];
}) {
  const maxF1 = Math.max(...rows.map((r) => r.f1_crisis));
  const nTest = rows[0]?.n_test;
  const nCrisis = rows[0]?.n_test_crisis;
  return (
    <div className="flex-1 min-w-0">
      <div className="flex flex-wrap items-baseline gap-2 mb-1">
        <h3 className="font-sans font-semibold text-[15px] text-text-primary">{title}</h3>
        <span
          className={`font-sans text-[11px] font-medium px-1.5 py-0.5 border ${
            verdict === "beats"
              ? "border-text-primary text-text-primary"
              : "border-accent text-accent"
          }`}
        >
          {verdict === "beats" ? "beats baseline" : "loses to baseline"}
        </span>
        {verdict === "loses" && <InfoTip k="baselineWins" label="Why the baseline wins here" />}
      </div>
      <p className="font-sans text-[12.5px] text-text-muted mb-1 max-w-md">{description}</p>
      {nTest != null && nCrisis != null && (
        <p className="font-mono text-[11px] text-text-muted mb-3">
          tested on {nTest.toLocaleString()} hours, {nCrisis.toLocaleString()} of them real crisis hours
        </p>
      )}
      <div className="space-y-3">
        {rows.map((r) => {
          const isBaseline = r.scorer === "rule_based_baseline";
          const pct = (r.f1_crisis / maxF1) * 100;
          return (
            <div key={r.scorer}>
              <div className="flex justify-between items-baseline mb-1">
                <span className="font-sans text-[12.5px] text-text-secondary">
                  {SCORER_LABEL[r.scorer]}
                  {isBaseline && <span className="text-text-muted"> (existing)</span>}
                </span>
                <span className="font-mono text-[12.5px] font-medium text-text-primary font-tabular">
                  F1 {r.f1_crisis.toFixed(3)}
                </span>
              </div>
              <div className="h-[18px] bg-fill w-full">
                <div
                  className="h-full bg-text-primary rounded-r-[3px]"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="mt-0.5 font-mono text-[11px] text-text-muted font-tabular">
                precision {r.precision_crisis.toFixed(2)} · recall {r.recall_crisis.toFixed(2)} ·
                PR-AUC {r.pr_auc.toFixed(2)}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Def({ term, tip, children }: { term: string; tip: "precision" | "recall" | "f1" | "prauc"; children: React.ReactNode }) {
  return (
    <div className="border-t border-border pt-2">
      <dt className="font-sans text-[12.5px] font-semibold text-text-primary">
        {term}
        <InfoTip k={tip} label={term} />
      </dt>
      <dd className="font-sans text-[12.5px] leading-snug text-text-secondary mt-0.5">{children}</dd>
    </div>
  );
}

export default function ClassifierComparison({ rows }: { rows: ClassifierMetricRow[] }) {
  const testOnUst = rows.filter((r) => r.direction === "TEST_ON_UST");
  const testOnUsdc = rows.filter((r) => r.direction === "TEST_ON_USDC");

  return (
    <section id="classifier" aria-labelledby="classifier-heading" className="max-w-5xl mx-auto px-5 py-10 border-t border-border scroll-mt-4">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <ProcessTags types={["batch", "ml"]} />
        <InfoTip k="classifierSplit" label="Train on one coin, test on the other" />
      </div>
      <h2 id="classifier-heading" className="font-sans font-semibold text-[20px] text-text-primary mb-2 max-w-2xl">
        A model trained on the mild crisis beat the baseline detecting the severe one.
        Trained the other way, it lost.
      </h2>
      <WhatIsThis className="mb-2">
        A machine-learning model was trained on one coin&apos;s crisis pattern, then tested on
        the other&apos;s — a coin it never saw during training. Both directions are reported
        below, including the one where it lost, not just the flattering result.
      </WhatIsThis>
      <HowToRead className="mb-6">
        Each panel is one train→test direction with three scorers. Longer bar = higher F1, a
        balance of catching real crisis hours without too many false alarms. The line underneath
        gives the three numbers behind it (definitions below).
      </HowToRead>

      <div className="flex flex-col sm:flex-row gap-10 sm:gap-12">
        <DirectionPanel
          title="Trained on USDC → tested on UST"
          description="Never saw UST's algorithmic collapse during training. Still generalizes."
          verdict="beats"
          rows={testOnUst}
        />
        <DirectionPanel
          title="Trained on UST → tested on USDC"
          description="Trained on total collapse, tested on a milder bank-run depeg. Doesn't transfer."
          verdict="loses"
          rows={testOnUsdc}
        />
      </div>

      <div className="mt-10 grid grid-cols-1 md:grid-cols-2 gap-8">
        <div>
          <h3 className="font-sans font-semibold text-[15px] text-text-primary mb-2">The four numbers, in plain words</h3>
          <dl className="space-y-2">
            <Def term="Precision" tip="precision">
              Of the hours the detector flagged as crisis, how many really were. High = few false alarms.
            </Def>
            <Def term="Recall" tip="recall">
              Of the hours that really were crisis, how many it caught. High = few missed hours.
            </Def>
            <Def term="F1" tip="f1">
              The balance of the two (their harmonic mean). It is the bar length above.
            </Def>
            <Def term="PR-AUC" tip="prauc">
              Quality across every possible alert threshold, not just the one chosen. 1.0 is perfect.
            </Def>
          </dl>
          <p className="mt-3 border border-border bg-fill p-3 font-sans text-[12.5px] leading-snug text-text-secondary">
            <strong className="text-text-primary">Tiny worked example.</strong> Suppose 100 hours were truly
            crisis and a detector flags 80 hours, of which 72 are truly crisis. Precision = 72 ÷ 80 = 0.90.
            Recall = 72 ÷ 100 = 0.72. F1 = 2 × 0.90 × 0.72 ÷ (0.90 + 0.72) = 0.80.
          </p>
        </div>
        <div>
          <h3 className="font-sans font-semibold text-[15px] text-text-primary mb-2">Why it matters that it lost one direction</h3>
          <div className="font-sans text-[12.5px] leading-snug text-text-secondary space-y-2">
            <p>
              <strong className="text-text-primary">Why the rule-based baseline wins on USDC:</strong> its price
              and volume parts were built and validated on USDC&apos;s crisis, so USDC is close to home ground for
              it. A model trained on UST&apos;s total collapse transfers poorly to USDC&apos;s milder bank-run
              depeg because the two failures are structurally different.
            </p>
            <p>
              <strong className="text-text-primary">Why report it:</strong> this is a test across two real
              events, not a claim of general predictive power. Showing the loss keeps the result honest. A first
              training run also had a leakage-adjacent feature (a window-constant wallet-concentration value that
              acted as a proxy for the label), which was removed before these numbers were produced.
            </p>
            <p>
              <strong className="text-text-primary">How it was split:</strong> labels come from independently known
              crisis dates, not from this project&apos;s own scores, so the model cannot just copy the baseline.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
