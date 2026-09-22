import type { ClassifierMetricRow } from "@/lib/data";

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
  return (
    <div className="flex-1 min-w-0">
      <div className="flex items-baseline gap-2 mb-1">
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
      </div>
      <p className="font-sans text-[13px] text-text-muted mb-4 max-w-md">{description}</p>
      <div className="space-y-2.5">
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
                <span className="font-mono text-[13px] font-medium text-text-primary font-tabular">
                  F1 {r.f1_crisis.toFixed(3)}
                </span>
              </div>
              <div className="h-[18px] bg-fill w-full">
                <div
                  className="h-full bg-text-primary rounded-r-[3px]"
                  style={{ width: `${pct}%` }}
                />
              </div>
              <div className="mt-0.5 font-mono text-[10.5px] text-text-muted font-tabular">
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

export default function ClassifierComparison({ rows }: { rows: ClassifierMetricRow[] }) {
  const testOnUst = rows.filter((r) => r.direction === "TEST_ON_UST");
  const testOnUsdc = rows.filter((r) => r.direction === "TEST_ON_USDC");

  return (
    <section aria-labelledby="classifier-heading" className="max-w-5xl mx-auto px-5 py-10 border-t border-border">
      <h2 id="classifier-heading" className="font-sans font-semibold text-[20px] text-text-primary mb-2 max-w-2xl">
        A model trained on the mild crisis beat the baseline detecting the severe one.
        Trained the other way, it lost.
      </h2>
      <p className="font-sans text-[13px] text-text-muted mb-8 max-w-2xl">
        A machine-learning model was trained on one coin&apos;s crisis pattern, then tested on
        the other&apos;s — a coin it never saw during training. Both directions are reported
        below, including the one where it lost, not just the flattering result. Longer bars
        mean a better balance of catching real crisis hours without too many false alarms
        (the F1 score); the numbers underneath spell that balance out directly.
      </p>
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
    </section>
  );
}
