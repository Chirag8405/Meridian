import type { EvaluationSummaryRow } from "@/lib/data";
import type { InfoKey } from "@/lib/explain";
import LeadTimeDiagram from "./LeadTimeDiagram";
import InfoTip from "./InfoTip";
import { HowToRead, ProcessTags, WhatIsThis } from "./Explain";

function fmtUsd(n: number): string {
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}K`;
  return `$${n.toFixed(0)}`;
}

function Row({
  label,
  tip,
  usdc,
  ust,
  note,
}: {
  label: string;
  tip: InfoKey;
  usdc: React.ReactNode;
  ust: React.ReactNode;
  note?: string;
}) {
  return (
    <tr className="border-b border-border/60">
      <th scope="row" className="font-sans text-[12.5px] font-normal text-text-secondary py-2.5 pr-4 align-top w-[34%] text-left">
        {label}
        <InfoTip k={tip} label={label} />
        {note && <div className="font-sans text-[13px] text-text-muted mt-0.5">{note}</div>}
      </th>
      <td className="font-mono text-[12.5px] text-text-primary py-2.5 pr-4 align-top">{usdc}</td>
      <td className="font-mono text-[12.5px] text-text-primary py-2.5 align-top">{ust}</td>
    </tr>
  );
}

export default function EvaluationTable({ usdc, ust }: { usdc: EvaluationSummaryRow; ust: EvaluationSummaryRow }) {
  const volRatio = (r: EvaluationSummaryRow) => (r.crisis_avg_volume_usd / r.calm_avg_volume_usd).toFixed(1);

  return (
    <div>
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <h2 className="font-sans font-semibold text-[17px] text-text-primary">Results table</h2>
        <ProcessTags types={["batch"]} />
      </div>
      <WhatIsThis className="mb-2">
        The same measurements for both crises, side by side. Each row has an <em>i</em> button saying what it
        means and how it is computed. The first column is the metric; the next two are USDC and UST.
      </WhatIsThis>
      <HowToRead className="mb-4">
        Read down the USDC column for the success case and down the UST column for the limit. The
        row to focus on is <strong className="text-text-primary">Lead time</strong>: 72 h for USDC against 0 h
        for UST. The small grey text under a row is a caveat that changes how the number should be read.
      </HowToRead>
      <table className="w-full border-collapse mb-10">
        <caption className="sr-only">Early-warning evaluation metrics for USDC (March 2023) and UST (May 2022)</caption>
        <thead>
          <tr className="border-b border-border">
            <th scope="col" className="text-left font-sans text-[11px] font-medium text-text-muted pb-2">Metric</th>
            <th scope="col" className="text-left font-sans text-[11px] font-medium text-text-muted pb-2">USDC · March 2023</th>
            <th scope="col" className="text-left font-sans text-[11px] font-medium text-text-muted pb-2">UST · May 2022</th>
          </tr>
        </thead>
        <tbody>
          <Row
            label="Depeg magnitude"
            tip="magnitude"
            usdc={`${usdc.depeg_magnitude_pct.toFixed(1)}% ($${usdc.min_price.toFixed(4)})`}
            ust={`${ust.depeg_magnitude_pct.toFixed(1)}% ($${ust.min_price.toFixed(4)})`}
          />
          <Row
            label="Lead time (first warning → depeg onset)"
            tip="leadTime"
            usdc={usdc.lead_time_hours > 0 ? `${usdc.lead_time_hours}h (${(usdc.lead_time_hours / 24).toFixed(1)}d)` : "0h"}
            ust={ust.lead_time_hours > 0 ? `${ust.lead_time_hours}h` : "0h"}
            note="0h means already elevated at the earliest available data, not a failure to warn"
          />
          <Row
            label="Peak stress score (0–100 scale)"
            tip="peakScore"
            usdc={usdc.peak_score.toFixed(1)}
            ust={ust.peak_score.toFixed(1)}
          />
          <Row
            label="Elevated threshold used"
            tip="threshold"
            usdc={usdc.elevated_threshold.toFixed(2)}
            ust={`${ust.elevated_threshold.toFixed(2)} (fixed, from USDC)`}
            note={ust.calm_caveat ?? undefined}
          />
          <Row
            label="False alarms (sustained elevation outside the crisis window)"
            tip="falseAlarms"
            usdc={`${usdc.false_alarm_count}`}
            ust={`${ust.false_alarm_count}`}
          />
          <Row
            label="Stayed elevated through the crisis window"
            tip="stayedElevated"
            usdc={`${usdc.crisis_hours_total - usdc.crisis_hours_below_threshold}/${usdc.crisis_hours_total}h`}
            ust={`${ust.crisis_hours_total - ust.crisis_hours_below_threshold}/${ust.crisis_hours_total}h`}
          />
          <Row
            label="Trading volume vs. calm baseline"
            tip="volumeRatio"
            usdc={`${volRatio(usdc)}× (${fmtUsd(usdc.calm_avg_volume_usd)} → ${fmtUsd(usdc.crisis_avg_volume_usd)})`}
            ust={`${volRatio(ust)}× (${fmtUsd(ust.calm_avg_volume_usd)} → ${fmtUsd(ust.crisis_avg_volume_usd)})`}
            note="Volume, not pool reserves/liquidity — reserve-balance history isn't available for the historical backfill"
          />
          <Row
            label="Recovery detected"
            tip="recovery"
            usdc={usdc.recovery_detected ? `Yes, ${usdc.recovery_delay_hours}h after window end` : "No"}
            ust={ust.recovery_na_permanent_collapse ? "N/A — permanent collapse" : ust.recovery_detected ? "Yes" : "No"}
          />
        </tbody>
      </table>

      <div className="flex flex-wrap items-center gap-2 mb-2">
        <h2 className="font-sans font-semibold text-[17px] text-text-primary">Lead-time timelines</h2>
        <InfoTip k="leadDiagram" label="Lead-time timeline" />
      </div>
      <WhatIsThis className="mb-2">
        The lead time drawn as a timeline: the moment the score first raised a sustained alarm, and the moment the
        price visibly broke.
      </WhatIsThis>
      <HowToRead className="mb-5">
        Left dot (black) = first warning from the score. Right dot (red) = depeg onset seen in the price.
        The distance between them, labelled in hours, is the lead time. A single red dot means the score was already
        high at the first hour of data, so there is nothing to the left to measure.
      </HowToRead>
      <div className="flex flex-col sm:flex-row gap-10 sm:gap-12">
        <div className="flex-1 min-w-0">
          <h3 className="font-sans font-semibold text-[15px] text-text-primary mb-3">USDC · March 2023</h3>
          <LeadTimeDiagram row={usdc} />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="font-sans font-semibold text-[15px] text-text-primary mb-3">UST · May 2022</h3>
          <LeadTimeDiagram row={ust} />
        </div>
      </div>
    </div>
  );
}
