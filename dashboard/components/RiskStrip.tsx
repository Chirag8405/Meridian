import type { CurrentRiskRow } from "@/lib/data";
import RiskGauge from "./RiskGauge";
import InfoTip from "./InfoTip";
import { HowToRead, ProcessTags, WhatIsThis } from "./Explain";

function formatDt(dt: string) {
  return new Date(dt + "T00:00:00Z").toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

export default function RiskStrip({ rows }: { rows: CurrentRiskRow[] }) {
  return (
    <section id="risk" aria-labelledby="risk-heading" className="max-w-5xl mx-auto px-5 pt-10 pb-8 scroll-mt-4">
      <div className="flex flex-wrap items-center gap-2 mb-1">
        <h2 id="risk-heading" className="font-sans font-semibold text-[17px] text-text-primary">
          Risk score, last observed reading per pair
        </h2>
        <ProcessTags types={["batch", "ml"]} />
        <InfoTip k="riskScore" label="Risk score (0–100)" />
      </div>
      <WhatIsThis className="mb-2">
        One 0–100 score per pair and exchange: the latest hour available for that pair. It
        combines four signals — how far price has moved off $1 (40%), how unusual trading volume
        and trade count are (25%), which stress pattern a K-Means model assigns the hour to
        (15%), and how concentrated trading is among a few wallets (20%).
      </WhatIsThis>
      <HowToRead className="mb-5">
        Bigger number and a bar past the thin line = more stress. The tag under the bar says
        whether the pair had a genuine calm period to compare against. Each pair&apos;s own
        dataset ends on a different date, so the reading is that pair&apos;s last available
        hour, not &quot;today.&quot;
        <InfoTip k="asOf" label="“as of” date" />
      </HowToRead>
      <div className="flex flex-wrap border-t border-l border-border">
        {rows.map((r) => {
          const elevated = r.baseline_status === "NO_RELIABLE_BASELINE";
          return (
            <div
              key={`${r.pair}-${r.project}`}
              className="bg-surface p-4 border-r border-b border-border basis-full sm:basis-1/2 lg:basis-1/4 grow"
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
                  <>
                    <span className="text-accent font-medium">elevated · no reliable baseline</span>
                    <InfoTip k="baselineNone" label="No reliable baseline" />
                  </>
                ) : (
                  <>
                    <span className="text-text-muted">reliable baseline</span>
                    <InfoTip k="baselineReliable" label="Reliable baseline" />
                  </>
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
