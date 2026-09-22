export default function IntroExplainer() {
  return (
    <section className="max-w-5xl mx-auto px-5 pt-4 pb-6">
      <div className="border border-border bg-fill p-4 sm:p-5">
        <p className="font-sans text-[13.5px] leading-relaxed text-text-secondary max-w-3xl">
          A <strong className="text-text-primary font-semibold">stablecoin</strong> is a
          cryptocurrency designed to always be worth $1. Sometimes it isn&apos;t — a{" "}
          <strong className="text-text-primary font-semibold">depeg</strong>. By the time that
          shows up on a price chart, the damage is often already done. This page tracks how
          on-chain trading behavior — not price — looked in the run-up to two real depegs, and
          uses the same method to score current trading in real time below.
        </p>
        <p className="font-sans text-[12px] leading-relaxed text-text-muted mt-2 max-w-3xl">
          Every risk number on this page is on the same 0–100 scale: 0 is a normal, quiet
          market; higher means trading looks more like the historical crises this page is
          validated against. Look for the small bar under each score — it shows exactly where
          that reading falls on that scale.
        </p>
      </div>
    </section>
  );
}
