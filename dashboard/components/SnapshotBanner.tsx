import type { Metadata } from "@/lib/data";
import { ProcessTag } from "./Explain";

export default function SnapshotBanner({ meta }: { meta: Metadata }) {
  return (
    <section id="live-vs-frozen" aria-labelledby="live-vs-frozen-heading" className="w-full border-t border-border scroll-mt-4">
      <div className="max-w-5xl mx-auto px-5 py-8">
        <div className="border border-border bg-fill p-4 sm:p-5">
          <h2 id="live-vs-frozen-heading" className="font-sans font-semibold text-[17px] text-text-primary mb-2">
            A note on what&apos;s live and what isn&apos;t
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <div className="mb-1.5">
                <ProcessTag type="streaming" />
              </div>
              <p className="font-sans text-[13px] leading-relaxed text-text-secondary">
                <strong className="text-text-primary">Live:</strong> the &quot;Live now&quot; scores and
                prices and the &quot;Recent activity&quot; panel, streamed from an Alchemy WebSocket
                connection to Ethereum. Live scores update when the batch export is republished; recent
                activity updates within seconds while the feed runs.
              </p>
            </div>
            <div>
              <div className="mb-1.5">
                <ProcessTag type="batch" />
              </div>
              <p className="font-sans text-[13px] leading-relaxed text-text-secondary">
                <strong className="text-text-primary">Frozen:</strong> the crisis case studies, classifier results
                and wallet rankings come from a fixed historical dataset. USDC data ends{" "}
                <span className="font-mono">{meta.dataset_end_usdc}</span>, UST data ends{" "}
                <span className="font-mono">{meta.dataset_end_ust}</span>, and neither updates.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
