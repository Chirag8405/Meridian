import type { EvaluationSummaryRow } from "@/lib/data";

const WIDTH = 560;
const HEIGHT = 90;
const PAD = 24;

function formatTime(iso: string) {
  return new Date(iso).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "UTC",
  }) + " UTC";
}

export default function LeadTimeDiagram({ row }: { row: EvaluationSummaryRow }) {
  const hasLead = row.first_warning_ts !== null && row.depeg_onset_ts !== null && row.lead_time_hours > 0;

  if (!row.depeg_onset_ts) {
    return (
      <p className="font-sans text-[12.5px] text-text-muted">
        No sustained depeg onset detected in the search window.
      </p>
    );
  }

  if (!hasLead) {
    return (
      <div>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full h-auto" role="img"
          aria-label={`${row.event_label}: no measurable lead time`}>
          <line x1={PAD} x2={WIDTH - PAD} y1={HEIGHT / 2} y2={HEIGHT / 2} stroke="var(--border)" strokeWidth={2} />
          <circle cx={PAD} cy={HEIGHT / 2} r={5} fill="var(--accent)" />
          <text x={PAD} y={HEIGHT / 2 - 14} textAnchor="start" className="font-mono fill-text-primary" fontSize={11} fontWeight={600}>
            already elevated
          </text>
          <text x={PAD} y={HEIGHT / 2 + 22} textAnchor="start" className="font-mono fill-text-muted" fontSize={10}>
            {formatTime(row.depeg_onset_ts)}
          </text>
        </svg>
        <p className="font-sans text-[12px] text-text-muted mt-1 max-w-md">
          Score is above threshold at the earliest available data for this pair — zero
          measurable lead time, because there&apos;s no genuine &quot;before&quot; in this dataset
          to measure from.
        </p>
      </div>
    );
  }

  const firstWarning = row.first_warning_ts!;
  const onset = row.depeg_onset_ts!;
  const x1 = PAD;
  const x2 = WIDTH - PAD;
  const midY = HEIGHT / 2;

  return (
    <div>
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} className="w-full h-auto" role="img"
        aria-label={`${row.event_label}: ${row.lead_time_hours} hour lead time between first warning and depeg onset`}>
        <line x1={x1} x2={x2} y1={midY} y2={midY} stroke="var(--border)" strokeWidth={2} />
        <line x1={x1} x2={x2} y1={midY} y2={midY} stroke="var(--text-primary)" strokeWidth={2}
          strokeDasharray="2 3" opacity={0.5} />

        <circle cx={x1} cy={midY} r={5} fill="var(--text-primary)" />
        <text x={x1} y={midY - 14} textAnchor="start" className="font-mono fill-text-primary" fontSize={11} fontWeight={600}>
          first warning
        </text>
        <text x={x1} y={midY + 22} textAnchor="start" className="font-mono fill-text-muted" fontSize={10}>
          {formatTime(firstWarning)}
        </text>

        <circle cx={x2} cy={midY} r={5} fill="var(--accent)" />
        <text x={x2} y={midY - 14} textAnchor="end" className="font-mono fill-accent" fontSize={11} fontWeight={600}>
          depeg onset
        </text>
        <text x={x2} y={midY + 22} textAnchor="end" className="font-mono fill-text-muted" fontSize={10}>
          {formatTime(onset)}
        </text>

        <text x={(x1 + x2) / 2} y={midY - 24} textAnchor="middle" className="font-mono fill-text-primary" fontSize={13} fontWeight={700}>
          {row.lead_time_hours}h lead time
        </text>
      </svg>
    </div>
  );
}
