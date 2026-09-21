import type { Metadata } from "@/lib/data";

export default function SnapshotBanner({ meta }: { meta: Metadata }) {
  return (
    <div className="w-full border-y-2 border-text-primary bg-fill">
      <div className="max-w-5xl mx-auto px-5 py-4 sm:py-3">
        <p className="font-sans text-[14px] sm:text-[13px] leading-snug text-text-primary">
          <strong className="font-semibold">
            This is a historical replay, not a live feed.
          </strong>{" "}
          Every figure on this page is computed from a fixed, frozen dataset — USDC data
          ends <span className="font-mono">{meta.dataset_end_usdc}</span>, UST data ends{" "}
          <span className="font-mono">{meta.dataset_end_ust}</span>. There is no streaming
          consumer yet (see the project roadmap), so nothing here updates in real time.
        </p>
      </div>
    </div>
  );
}
