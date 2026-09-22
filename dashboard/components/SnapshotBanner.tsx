import type { Metadata } from "@/lib/data";

export default function SnapshotBanner({ meta }: { meta: Metadata }) {
  return (
    <div className="w-full border-t border-border">
      <div className="max-w-5xl mx-auto px-5 py-5">
        <p className="font-sans text-[12.5px] leading-relaxed text-text-muted max-w-2xl">
          <strong className="text-text-secondary font-medium">A note on what&apos;s live and what isn&apos;t:</strong>{" "}
          the crisis case studies, classifier results, and wallet rankings above are computed
          from a fixed, frozen dataset — USDC data ends{" "}
          <span className="font-mono">{meta.dataset_end_usdc}</span>, UST data ends{" "}
          <span className="font-mono">{meta.dataset_end_ust}</span>, and neither updates. Only
          the &quot;Live now&quot; section is a genuine live feed, streaming directly from an
          Alchemy WebSocket connection to Ethereum.
        </p>
      </div>
    </div>
  );
}
