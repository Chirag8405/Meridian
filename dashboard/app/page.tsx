import {
  getCurrentRisk,
  getLiveRisk,
  getUsdcTimeline,
  getUstTimeline,
  getClassifierMetrics,
  getWalletRankings,
  getMetadata,
} from "@/lib/data";
import SnapshotBanner from "@/components/SnapshotBanner";
import LiveNow from "@/components/LiveNow";
import RiskStrip from "@/components/RiskStrip";
import CrisisChart from "@/components/CrisisChart";
import ClassifierComparison from "@/components/ClassifierComparison";
import WalletRankings from "@/components/WalletRankings";

export default function Home() {
  const meta = getMetadata();
  const currentRisk = getCurrentRisk();
  const liveRisk = getLiveRisk();
  const usdcTimeline = getUsdcTimeline();
  const ustTimeline = getUstTimeline();
  const metrics = getClassifierMetrics();
  const wallets = getWalletRankings();

  return (
    <main>
      <header className="max-w-5xl mx-auto px-5 pt-8 pb-2 flex items-baseline justify-between gap-4">
        <div>
          <h1 className="font-sans font-semibold text-[20px] tracking-tight text-text-primary">
            Meridian
          </h1>
          <p className="font-sans text-[13px] text-text-muted mt-0.5">
            Stablecoin depeg &amp; liquidity-stress early warning — findings dashboard
          </p>
        </div>
      </header>

      <div className="mt-4">
        <SnapshotBanner meta={meta} />
      </div>

      <LiveNow rows={liveRisk} />
      <RiskStrip rows={currentRisk} />

      <section aria-labelledby="crisis-heading" className="max-w-5xl mx-auto px-5 py-10 border-t border-border">
        <h2 id="crisis-heading" className="font-sans font-semibold text-[22px] text-text-primary mb-2 max-w-2xl">
          USDC recovered. UST didn&apos;t.
        </h2>
        <p className="font-sans text-[13px] text-text-muted mb-8 max-w-2xl">
          Both charts share the same $0–$1.05 price axis, so the depth of each collapse is
          directly comparable, not just the numbers beside it.
        </p>
        <div className="flex flex-col sm:flex-row gap-10 sm:gap-12">
          <CrisisChart
            title="USDC · Curve 3pool, March 2023 (SVB exposure)"
            dateRangeLabel={`${meta.usdc_crisis_window[0]} → ${meta.usdc_crisis_window[1]}`}
            points={usdcTimeline}
          />
          <CrisisChart
            title="UST · Curve metapool, May 2022 (algorithmic collapse)"
            dateRangeLabel={`${meta.ust_crisis_window[0]} → ${meta.ust_crisis_window[1]}`}
            points={ustTimeline}
          />
        </div>
      </section>

      <ClassifierComparison rows={metrics} />
      <WalletRankings rows={wallets} />

      <footer className="max-w-5xl mx-auto px-5 py-10 border-t border-border">
        <p className="font-mono text-[11px] text-text-muted">
          Data exported {new Date(meta.exported_at).toLocaleString("en-US", {
            dateStyle: "medium",
            timeStyle: "short",
          })}
          . Source: Hadoop/Hive/Spark pipeline, see project FINDINGS.md and ARCHITECTURE.md.
        </p>
      </footer>
    </main>
  );
}
