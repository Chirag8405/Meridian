import type { CurrentRiskRow } from "@/lib/data";
import RiskGauge from "./RiskGauge";

function formatDt(dt: string) {
  return new Date(dt + "T00:00:00Z").toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function RiskStrip({ rows }: { rows: CurrentRiskRow[] }) {
  return (
    <section aria-labelledby="risk-heading" className="max-w-5xl mx-auto px-5 pt-10 pb-8">
      <h2 id="risk-heading" className="font-sans font-semibold text-[17px] text-text-primary mb-1">
        Risk score, last observed reading per pair
      </h2>
      <p className="font-sans text-[13px] text-text-muted mb-5 max-w-2xl">
        A 0–100 score built from four signals: how far price has moved off $1, how unusual
        trading volume is, which stress pattern a K-Means model assigns the hour to, and how
        concentrated trading is among a few wallets. Each pair&apos;s own dataset ends on a
        different date — the reading shown is that pair&apos;s last available hour, not
        &quot;today.&quot;
      </p>
      <div className="flex flex-wrap border-t border-l border-border">
        {rows.map((r) => {
          const elevated = r.baseline_status === "NO_RELIABLE_BASELINE";
          return (
            <div
              key={`${r.pair}-${r.project}`}
              className="bg-surface p-4 border-r border-b border-border basis-1/2 sm:basis-1/4 grow"
            >
              <div className="font-mono text-[11px] text-text-muted mb-2 truncate">
                {r.pair} · {r.project}
              </div>
              <div
                className={`font-mono text-[26px] font-medium leading-none ${
                  elevated ? "text-accent" : "text-text-primary"
                }`}
              >
                {r.risk_score.toFixed(1)}
              </div>
              <RiskGauge score={r.risk_score} />
              <div className="mt-2 text-[11px] font-sans">
                {elevated ? (
                  <span className="text-accent font-medium">elevated · no reliable baseline</span>
                ) : (
                  <span className="text-text-muted">reliable baseline</span>
                )}
              </div>
              <div className="mt-1 font-mono text-[10px] text-text-muted">
                as of {formatDt(r.dt)}
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
