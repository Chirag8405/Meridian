import {
  getCurrentRisk,
  getLiveRisk,
  getUsdcTimeline,
  getUstTimeline,
  getLivePriceTimeline,
  getRecentSwapEvents,
  getRecentSwapActivity,
  getClassifierMetrics,
  getWalletRankings,
  getEvaluationSummary,
  getMetadata,
} from "@/lib/data";
import SiteNav from "@/components/SiteNav";
import SnapshotBanner from "@/components/SnapshotBanner";
import IntroExplainer from "@/components/IntroExplainer";
import LiveNow from "@/components/LiveNow";
import RecentActivity from "@/components/RecentActivity";
import RiskStrip from "@/components/RiskStrip";
import CrisisChart from "@/components/CrisisChart";
import ClassifierComparison from "@/components/ClassifierComparison";
import WalletRankings from "@/components/WalletRankings";
import TechStackCard from "@/components/TechStackCard";
import Glossary from "@/components/Glossary";
import InfoTip from "@/components/InfoTip";
import { ProcessTags, WhatIsThis } from "@/components/Explain";

export default async function Home() {
  const meta = await getMetadata();
  const currentRisk = await getCurrentRisk();
  const liveRisk = await getLiveRisk();
  const usdcTimeline = await getUsdcTimeline();
  const ustTimeline = await getUstTimeline();
  const livePriceTimeline = await getLivePriceTimeline();
  const recentSwapEvents = await getRecentSwapEvents();
  const recentSwapActivity = await getRecentSwapActivity();
  const metrics = await getClassifierMetrics();
  const wallets = await getWalletRankings();
  const evaluation = await getEvaluationSummary();

  return (
    <main>
      <header className="max-w-5xl mx-auto px-5 pt-8 pb-2 flex flex-wrap items-baseline justify-between gap-4">
        <div>
          <h1 className="font-sans font-semibold text-[20px] tracking-tight text-text-primary">
            Meridian
          </h1>
          <p className="font-sans text-[13px] text-text-muted mt-0.5">
            Stablecoin depeg &amp; liquidity-stress early warning — findings dashboard
          </p>
        </div>
        <SiteNav current="home" />
      </header>

      <IntroExplainer evaluation={evaluation} />

      <LiveNow rows={liveRisk} priceTimeline={livePriceTimeline} />
      <RecentActivity events={recentSwapEvents} activity={recentSwapActivity} />
      <RiskStrip rows={currentRisk} />

      <section id="crisis" aria-labelledby="crisis-heading" className="max-w-5xl mx-auto px-5 py-10 border-t border-border scroll-mt-4">
        <div className="flex flex-wrap items-center gap-2 mb-2">
          <ProcessTags types={["batch"]} />
          <InfoTip k="crisisChart" label="Crisis timelines" />
        </div>
        <h2 id="crisis-heading" className="font-sans font-semibold text-[22px] text-text-primary mb-2 max-w-2xl">
          USDC recovered. UST didn&apos;t.
        </h2>
        <WhatIsThis className="mb-2">
          Two real depegs, plotted on the same $0–$1.05 price axis so the depth of each
          collapse is directly comparable. USDC (March 2023) lost its peg for days after its
          issuer disclosed exposure to Silicon Valley Bank, then fully recovered. UST (May
          2022), an algorithmic stablecoin with no such backing, collapsed and never came back.
        </WhatIsThis>
        <p className="font-sans text-[12.5px] leading-relaxed text-text-muted mb-8 max-w-2xl">
          <span className="font-medium text-text-secondary">Why the same axis? </span>
          With both charts running from $0 to $1.05, a dip to $0.88 and a collapse to $0.03 look as
          different as they really are. A zoomed axis would make both look like the same crash.
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

      <SnapshotBanner meta={meta} />

      <TechStackCard />
      <Glossary />

      <footer className="max-w-5xl mx-auto px-5 py-6 border-t border-border">
        <p className="font-mono text-[11px] text-text-muted">
          Data exported {new Date(meta.exported_at).toLocaleString("en-US", {
            dateStyle: "medium",
            timeStyle: "short",
          })}
          . Source: Hadoop/Hive/Spark pipeline, see project docs/FINDINGS.md and docs/ARCHITECTURE.md.
          The &quot;Live now&quot; scores are as fresh as this export.
        </p>
      </footer>
    </main>
  );
}
