import type { WalletRankingRow } from "@/lib/data";

function shortAddr(addr: string) {
  return `${addr.slice(0, 10)}…${addr.slice(-6)}`;
}

function RankTable({ title, rows }: { title: string; rows: WalletRankingRow[] }) {
  const contracts = rows.filter((r) => r.is_contract).length;
  return (
    <div className="flex-1 min-w-0">
      <h3 className="font-sans font-semibold text-[15px] text-text-primary mb-1">{title}</h3>
      <p className="font-sans text-[12.5px] text-text-muted mb-3">
        {contracts} of top {rows.length} are contracts, not EOA traders
      </p>
      <table className="w-full border-collapse">
        <thead>
          <tr className="border-b border-border">
            <th className="text-left font-sans text-[11px] font-medium text-text-muted pb-1.5 pr-2">
              rank
            </th>
            <th className="text-left font-sans text-[11px] font-medium text-text-muted pb-1.5 pr-2">
              address
            </th>
            <th className="text-left font-sans text-[11px] font-medium text-text-muted pb-1.5 pr-2">
              type
            </th>
            <th className="text-right font-sans text-[11px] font-medium text-text-muted pb-1.5">
              score
            </th>
          </tr>
        </thead>
        <tbody>
          {rows.slice(0, 5).map((r) => (
            <tr key={r.node_id} className="border-b border-border/60 last:border-0">
              <td className="font-mono text-[12px] text-text-muted py-1.5 pr-2 font-tabular">
                {r.rank_within_window}
              </td>
              <td className="font-mono text-[12px] text-text-secondary py-1.5 pr-2">
                {shortAddr(r.node_id)}
              </td>
              <td className="font-sans text-[11.5px] py-1.5 pr-2">
                {r.is_contract ? (
                  <span className="text-text-primary font-medium">contract</span>
                ) : (
                  <span className="text-text-muted">EOA</span>
                )}
              </td>
              <td className="font-mono text-[12px] text-text-primary py-1.5 text-right font-tabular">
                {r.pagerank_score.toFixed(4)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function WalletRankings({ rows }: { rows: WalletRankingRow[] }) {
  const usdc = rows.filter((r) => r.window_label === "USDC_MAR2023_CRISIS");
  const ust = rows.filter((r) => r.window_label === "UST_MAY2022_CRISIS");
  const totalContracts = rows.filter((r) => r.is_contract).length;

  return (
    <section aria-labelledby="wallet-heading" className="max-w-5xl mx-auto px-5 py-10 border-t border-border">
      <h2 id="wallet-heading" className="font-sans font-semibold text-[20px] text-text-primary mb-2 max-w-2xl">
        Who trades during a crisis? Mostly infrastructure, not people.
      </h2>
      <p className="font-sans text-[13px] text-text-muted mb-8 max-w-2xl">
        Weighted PageRank on a bipartite wallet↔pool graph, top-ranked addresses per crisis
        window. Verified against on-chain bytecode (<span className="font-mono">eth_getCode</span>),
        not inferred from address patterns — {totalContracts} of {rows.length} shown here are
        contracts. A high rank means &quot;a lot of volume routes through this address,&quot; not
        &quot;this is an influential trader.&quot;
      </p>
      <div className="flex flex-col sm:flex-row gap-10 sm:gap-12">
        <RankTable title="USDC · March 2023" rows={usdc} />
        <RankTable title="UST · May 2022" rows={ust} />
      </div>
    </section>
  );
}
