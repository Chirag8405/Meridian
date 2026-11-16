import { TECH_STACK } from "@/lib/glossary";
import { ProcessTags } from "./Explain";

export default function TechStackCard() {
  return (
    <section aria-labelledby="stack-heading" className="max-w-5xl mx-auto px-5 py-10 border-t border-border">
      <div className="flex flex-wrap items-center gap-2 mb-2">
        <h2 id="stack-heading" className="font-sans font-semibold text-[20px] text-text-primary">
          Tech stack &amp; pipeline summary
        </h2>
        <ProcessTags types={["batch", "streaming", "ml"]} />
      </div>
      <p className="font-sans text-[12.5px] text-text-muted mb-5 max-w-2xl">
        <span className="font-semibold text-text-secondary">What am I looking at? </span>
        Every technology in the project and the one job it does. Versions are the ones pinned in
        the project&apos;s CLAUDE.md.
      </p>
      <dl className="border-t border-l border-border grid grid-cols-1 md:grid-cols-2">
        {TECH_STACK.map((t) => (
          <div key={t.tech} className="border-r border-b border-border p-3.5">
            <dt className="font-mono text-[12px] font-semibold text-text-primary">{t.tech}</dt>
            <dd className="font-sans text-[12.5px] leading-snug text-text-secondary mt-1">{t.role}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
