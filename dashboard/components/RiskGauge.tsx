// Historical USDC_CRISIS average from docs/FINDINGS.md's risk_score
// validation table — a real number from this project's own data, not an
// invented threshold. (RELIABLE_CALM's average, 4.73, sits too close to 0
// on this 0-100 scale to mark usefully — the calm end of the axis already
// says that.) Live tracking is USDC-only (see spark/stream_alchemy_live.scala),
// so the USDC crisis reference is the directly comparable one.
const HISTORICAL_CRISIS_AVG = 21.35;

export default function RiskGauge({ score }: { score: number }) {
  const pct = Math.min(100, Math.max(0, score));
  const crisisPct = Math.min(100, HISTORICAL_CRISIS_AVG);
  const severe = score >= HISTORICAL_CRISIS_AVG;

  return (
    <div className="mt-2.5">
      <div className="relative h-[7px] bg-fill w-full">
        <div
          className={`h-full transition-[width] duration-500 ${severe ? "bg-accent" : "bg-text-primary"}`}
          style={{ width: `${pct}%` }}
        />
        <div
          className="absolute -top-0.5 -bottom-0.5 w-px bg-text-muted/70"
          style={{ left: `${crisisPct}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between font-mono text-[9.5px] text-text-muted">
        <span>0 · calm</span>
        <span title={`Historical USDC crisis average: ${HISTORICAL_CRISIS_AVG}`}>
          ↑ typical crisis
        </span>
        <span>100</span>
      </div>
    </div>
  );
}
