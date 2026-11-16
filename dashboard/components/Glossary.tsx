import { GLOSSARY } from "@/lib/glossary";

export default function Glossary() {
  return (
    <section id="glossary" aria-labelledby="glossary-heading" className="max-w-5xl mx-auto px-5 py-10 border-t border-border scroll-mt-4">
      <h2 id="glossary-heading" className="font-sans font-semibold text-[20px] text-text-primary mb-2">
        Glossary
      </h2>
      <p className="font-sans text-[12.5px] text-text-muted mb-6 max-w-2xl">
        <span className="font-semibold text-text-secondary">What am I looking at? </span>
        Plain-language definitions of every technical term used on this site: market terms
        first, then the models, then the Big Data tools.
      </p>
      <dl className="grid grid-cols-1 md:grid-cols-2 gap-x-10 gap-y-4">
        {GLOSSARY.map((g) => (
          <div key={g.term} className="border-t border-border pt-3">
            <dt className="font-sans text-[13px] font-semibold text-text-primary">{g.term}</dt>
            <dd className="font-sans text-[12.5px] leading-snug text-text-secondary mt-0.5">{g.def}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
