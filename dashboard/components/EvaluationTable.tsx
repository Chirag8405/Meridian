import type { EvaluationSummaryRow } from "@/lib/data";
import LeadTimeDiagram from "./LeadTimeDiagram";

function fmtUsd(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function Row({ label, usdc, ust, note }: { label: string; usdc: React.ReactNode; ust: React.ReactNode; note?: string }) {
  return (
    <tr className="border-b border-border/60">
      <td className="font-sans text-[12.5px] text-text-muted py-2.5 pr-4 align-top w-[30%]">
        {label}
        {note && <div className="font-sans text-[10.5px] text-text-muted/80 mt-0.5">{note}</div>}
      </td>
      <td className="font-mono text-[13px] text-text-primary py-2.5 pr-4 align-top">{usdc}</td>
      <td className="font-mono text-[13px] text-text-primary py-2.5 align-top">{ust}</td>
    </tr>
  );
}

export default function EvaluationTable({ usdc, ust }: { usdc: EvaluationSummaryRow; ust: EvaluationSummaryRow }) {
  const volRatio = (r: EvaluationSummaryRow) => (r.crisis_avg_volume_usd / r.calm_avg_volume_usd).toFixed(1);

  return (
    <div>
      <table className="w-full border-collapse mb-8">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left font-sans text-[11px] font-medium text-text-muted pb-2">Metric</th>
            <th className="text-left font-sans text-[11px] font-medium text-text-muted pb-2">USDC · March 2023</th>
            <th className="text-left font-sans text-[11px] font-medium text-text-muted pb-2">UST · May 2022</th>
          </tr>
        </thead>
        <tbody>
          <Row
            label="Depeg magnitude"
            usdc={`${usdc.depeg_magnitude_pct.toFixed(1)}% ($${usdc.min_price.toFixed(4)})`}
            ust={`${ust.depeg_magnitude_pct.toFixed(1)}% ($${ust.min_price.toFixed(4)})`}
          />
          <Row
            label="Lead time (first warning → depeg onset)"
            usdc={usdc.lead_time_hours > 0 ? `${usdc.lead_time_hours}h (${(usdc.lead_time_hours / 24).toFixed(1)}d)` : "0h"}
            ust={ust.lead_time_hours > 0 ? `${ust.lead_time_hours}h` : "0h"}
            note="0h means already elevated at the earliest available data, not a failure to warn"
          />
          <Row
            label="Peak stress score (0–100 scale)"
            usdc={usdc.peak_score.toFixed(1)}
            ust={ust.peak_score.toFixed(1)}
          />
          <Row
            label="Elevated threshold used"
            usdc={usdc.elevated_threshold.toFixed(2)}
            ust={`${ust.elevated_threshold.toFixed(2)} (fixed, from USDC)`}
            note={ust.calm_caveat ?? undefined}
          />
          <Row
            label="False alarms (sustained elevation outside the crisis window)"
            usdc={`${usdc.false_alarm_count}`}
            ust={`${ust.false_alarm_count}`}
          />
          <Row
            label="Stayed elevated through the crisis window"
            usdc={`${usdc.crisis_hours_total - usdc.crisis_hours_below_threshold}/${usdc.crisis_hours_total}h`}
            ust={`${ust.crisis_hours_total - ust.crisis_hours_below_threshold}/${ust.crisis_hours_total}h`}
          />
          <Row
            label="Trading volume vs. calm baseline"
            usdc={`${volRatio(usdc)}× (${fmtUsd(usdc.calm_avg_volume_usd)} → ${fmtUsd(usdc.crisis_avg_volume_usd)})`}
            ust={`${volRatio(ust)}× (${fmtUsd(ust.calm_avg_volume_usd)} → ${fmtUsd(ust.crisis_avg_volume_usd)})`}
            note="Volume, not pool reserves/liquidity — reserve-balance history isn't available for the historical backfill"
          />
          <Row
            label="Recovery detected"
            usdc={usdc.recovery_detected ? `Yes, ${usdc.recovery_delay_hours}h after window end` : "No"}
            ust={ust.recovery_na_permanent_collapse ? "N/A — permanent collapse" : ust.recovery_detected ? "Yes" : "No"}
          />
        </tbody>
      </table>

      <div className="flex flex-col sm:flex-row gap-10 sm:gap-12">
        <div className="flex-1 min-w-0">
          <h3 className="font-sans font-semibold text-[14px] text-text-primary mb-3">USDC · March 2023</h3>
          <LeadTimeDiagram row={usdc} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-sans font-semibold text-[14px] text-text-primary mb-3">UST · May 2022</h3>
          <LeadTimeDiagram row={ust} />
        </div>
      </div>
    </div>
  );
}
