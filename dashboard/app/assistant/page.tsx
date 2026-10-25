import type { Metadata } from "next";
import Link from "next/link";
import Assistant from "@/components/Assistant";

// Public but unlisted for now: no link from the header, kept out of search
// results. See docs/GENAI_ASSISTANT_PLAN.md section 10, decision 3.
export const metadata: Metadata = {
  title: "Assistant · Meridian",
  robots: { index: false, follow: false },
};

export default function AssistantPage() {
  return (
    <main>
      <header className="max-w-5xl mx-auto px-5 pt-8 pb-2 flex items-baseline justify-between gap-4">
        <div>
          <h1 className="font-sans font-semibold text-[20px] tracking-tight text-text-primary">
            Ask Meridian
          </h1>
          <p className="font-sans text-[13px] text-text-muted mt-0.5">
            Questions about the live risk scores, the two real crises, and how the project works
          </p>
        </div>
        <Link
          href="/"
          className="font-sans text-[12px] font-medium px-2.5 py-1 border border-text-primary text-text-primary hover:bg-fill shrink-0"
        >
          ← Dashboard
        </Link>
      </header>
      <Assistant />
    </main>
  );
}
