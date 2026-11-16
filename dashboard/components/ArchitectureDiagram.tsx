import type { ReactNode } from "react";
import { ProcessTag, type ProcessType } from "./Explain";

// The real pipeline from docs/ARCHITECTURE.md, written as data so every box
// and arrow label can be audited against the repo. Table, job and file names
// are the ones in hive/*.sql, spark/*.scala, ingestion/*.py and backend/*.py.

type Node = {
  title: string;
  tech: string;
  desc: string;
  items?: string[];
  tags?: ProcessType[];
};

type Lane = {
  id: string;
  kind: ProcessType | "serve";
  heading: string;
  sub: string;
  nodes: Node[];
  /** edges[i] labels the arrow between nodes[i] and nodes[i + 1]. */
  edges: string[];
};

const LANES: Lane[] = [
  {
    id: "batch",
    kind: "batch",
    heading: "Batch path · frozen historical data",
    sub: "Run by hand as finite Spark/Hive jobs on the two real crises. Results do not change between runs.",
    nodes: [
      {
        title: "Dune Analytics",
        tech: "Dune SQL API · ingestion/dune_*.py",
        desc: "Historical on-chain swaps pulled once. Hourly pool aggregates plus raw wallet-level trades.",
        items: [
          "USDC pairs: Dec 2022 – May 2023",
          "UST pairs: Apr – Jun 2022",
          "~135K wallet-level trades",
        ],
      },
      {
        title: "Storage",
        tech: "HDFS + Hive 3.1.3 (+ Sqoop)",
        desc: "Files in HDFS exposed as SQL tables. The hourly table is ORC, partitioned by pair and date.",
        items: [
          "meridian.stablecoin_pool_hourly",
          "meridian.wallet_trades_raw",
          "Sqoop: curated incident records (per docs)",
        ],
      },
      {
        title: "Feature engineering",
        tech: "Spark SQL",
        desc: "Turns hourly rows into comparable signals, each measured against the pair's calm baseline.",
        items: [
          "price_dev, volume_dev, trade_count_dev (z-scores)",
          "anomaly_flag",
          "3h rolling mean, slope, velocity (classifier)",
          "tables: baseline_stats, crisis_stats, crisis_features",
        ],
      },
      {
        title: "Models",
        tech: "Spark MLlib · GraphX",
        desc: "Four analytics over the features. All batch, all run offline.",
        items: [
          "Rule-based risk score → risk_scores_baseline",
          "K-Means k = 4 → stress_clusters",
          "Logistic regression + random forest → crisis_classifier_metrics",
          "Weighted PageRank → wallet_pagerank, wallet_labels",
        ],
        tags: ["ml"],
      },
      {
        title: "Batch export",
        tech: "export_dashboard_data.scala · evaluation_summary.scala",
        desc: "Materialises the dashboard's queries as small JSON files, because the dashboard never queries Hive live.",
        items: ["dashboard/data/*.json"],
      },
    ],
    edges: [
      "hourly pool rows + wallet trades",
      "SQL tables read by Spark",
      "z-scores, flags, trend features",
      "scores, cluster ids, PageRank, metrics",
    ],
  },
  {
    id: "streaming",
    kind: "streaming",
    heading: "Streaming path · live Ethereum swaps",
    sub: "Meant to run continuously under systemd. Same Hive tables, same score formula, a frozen model.",
    nodes: [
      {
        title: "Alchemy WebSocket",
        tech: "eth_subscribe (logs) · Ethereum mainnet",
        desc: "Live swap events pushed the moment they happen from 3 pool contracts (4 pair/pool combinations).",
        items: ["Curve 3pool", "Uniswap V2 USDC/USDT", "Uniswap V2 USDC/DAI"],
      },
      {
        title: "Live feed script",
        tech: "ingestion/alchemy_live_feed.py (Python)",
        desc: "Decodes logs into an implied price, adds USD volume from CoinGecko, and gap-fills missed blocks with eth_getLogs after a disconnect.",
        items: ["source = alchemy_live or alchemy_getlogs_replay", "also publishes each SWAP to Supabase recent_swap_events"],
      },
      {
        title: "Landing directory",
        tech: "data/raw/alchemy_live_stream/",
        desc: "Small JSON files written atomically. Spark has no native WebSocket source, so files are the hand-off.",
      },
      {
        title: "Streaming consumer",
        tech: "Spark Structured Streaming · stream_alchemy_live.scala",
        desc: "Rolls swaps into 1-hour windows (2-hour watermark, 10-minute trigger) and scores them with the frozen K-Means model.",
        items: [".transform() only, never .fit()", "append output mode"],
        tags: ["ml"],
      },
      {
        title: "Same Hive tables",
        tech: "Hive",
        desc: "Live hours land next to the historical ones, told apart by the source column.",
        items: ["stablecoin_pool_hourly", "risk_scores_baseline"],
      },
    ],
    edges: [
      "raw swap + reserve logs",
      "decoded JSON events",
      "files read by Spark's File source",
      "hourly rows + risk scores appended",
    ],
  },
  {
    id: "serving",
    kind: "serve",
    heading: "Export & serving · how data reaches this page",
    sub: "Run by hand or by the systemd publish timer (every two hours when enabled). JSON updating alone changes nothing downstream.",
    nodes: [
      {
        title: "Spark export",
        tech: "spark-shell · export_dashboard_data.scala",
        desc: "Reads the Hive tables from both paths and writes the dashboard's result sets as JSON.",
        items: ["current_risk, current_risk_live", "timelines, classifier_metrics", "wallet_rankings, metadata"],
      },
      {
        title: "Risk advisories",
        tech: "Groq · generate_risk_advisories.py",
        desc: "Best-effort plain-English sentence per live score. If it fails, no advisory is shown.",
      },
      {
        title: "Supabase",
        tech: "Postgres · push_to_supabase.py",
        desc: "Holds the exported results. Public read-only via row-level security; writes need a secret key kept on the local machine.",
      },
      {
        title: "Read API",
        tech: "FastAPI on Render",
        desc: "Read-only API using a publishable key. Also aggregates recent swaps for the Recent activity panel.",
        items: ["/api/dashboard-data", "/api/recent-swap-activity"],
      },
      {
        title: "This dashboard",
        tech: "Next.js on Vercel",
        desc: "Server Components fetch the API (revalidate 60 s). Recent activity refreshes every 20 s from the browser.",
      },
    ],
    edges: [
      "JSON result sets",
      "rows with advisory text",
      "table rows (REST)",
      "combined JSON response",
    ],
  },
];

const LANE_STYLE: Record<Lane["kind"], string> = {
  batch: "border-l-text-primary",
  streaming: "border-l-accent",
  ml: "border-l-text-muted",
  serve: "border-l-border",
};

// Let long identifiers (table, job and file names) wrap at "_", "." and "/"
// instead of splitting mid-word.
function Ident({ text }: { text: string }) {
  const parts = text.split(/([_./])/);
  return (
    <>
      {parts.map((p, i) => (
        <span key={i}>
          {p}
          {/^[_./]$/.test(p) ? <wbr /> : null}
        </span>
      ))}
    </>
  );
}

function Arrow({ label }: { label: string }) {
  return (
    <li className="flex items-center justify-center gap-2 py-1.5 font-sans text-[12px] text-text-muted">
      <span aria-hidden="true">↓</span>
      <span className="italic">
        <span className="sr-only">then, passes: </span>
        {label}
      </span>
    </li>
  );
}

function NodeRow({ node, index }: { node: Node; index: number }) {
  return (
    <li className="grid grid-cols-1 gap-x-6 gap-y-1.5 border border-border bg-surface p-3 md:grid-cols-[210px_1fr]">
      <div className="min-w-0">
        <div className="flex items-start gap-2">
          <span
            aria-hidden="true"
            className="mt-px flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-text-primary font-mono text-[10px] text-text-primary"
          >
            {index + 1}
          </span>
          <h4 className="font-sans text-[13px] font-semibold leading-tight text-text-primary">{node.title}</h4>
        </div>
        <p className="mt-1 pl-6 font-mono text-[10.5px] leading-snug text-text-muted">
          <Ident text={node.tech} />
        </p>
      </div>
      <div className="min-w-0">
        <p className="font-sans text-[12.5px] leading-snug text-text-secondary">{node.desc}</p>
        {node.items && (
          <ul className="mt-1.5 grid grid-cols-1 gap-x-4 gap-y-0.5 sm:grid-cols-2">
            {node.items.map((it) => (
              <li key={it} className="font-mono text-[11px] leading-snug text-text-primary">
                · <Ident text={it} />
              </li>
            ))}
          </ul>
        )}
        {node.tags && (
          <div className="mt-2 flex flex-wrap gap-1">
            {node.tags.map((t) => (
              <ProcessTag key={t} type={t} />
            ))}
          </div>
        )}
      </div>
    </li>
  );
}

function LaneView({ lane }: { lane: Lane }) {
  return (
    <section
      aria-labelledby={`lane-${lane.id}`}
      className={`border border-border border-l-[3px] p-4 ${LANE_STYLE[lane.kind]}`}
    >
      <div className="mb-1 flex flex-wrap items-center gap-x-3 gap-y-1">
        {lane.kind !== "serve" && <ProcessTag type={lane.kind} />}
        <h3 id={`lane-${lane.id}`} className="font-sans text-[15px] font-semibold text-text-primary">
          {lane.heading}
        </h3>
      </div>
      <p className="mb-3 font-sans text-[12.5px] text-text-muted">{lane.sub}</p>
      <ol>
        {lane.nodes.flatMap((n, i) => {
          const out: ReactNode[] = [<NodeRow key={n.title} node={n} index={i} />];
          if (i < lane.edges.length) out.push(<Arrow key={`e-${i}`} label={lane.edges[i]} />);
          return out;
        })}
      </ol>
    </section>
  );
}

function Bridge({ children }: { children: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1 py-2 text-center" role="note">
      <span className="text-text-muted" aria-hidden="true">
        ↓
      </span>
      <p className="max-w-2xl font-sans text-[12.5px] leading-relaxed text-text-muted">{children}</p>
    </div>
  );
}

export default function ArchitectureDiagram() {
  return (
    <div>
      <LaneView lane={LANES[0]} />
      <Bridge>
        <strong className="font-medium text-text-secondary">Frozen hand-off, batch → streaming:</strong> the saved
        standard scaler and K-Means model (
        <code className="font-mono text-[11px]">spark/models/stress_clustering</code> on HDFS) plus the calm baseline
        statistics. The streaming job only applies them; it never re-fits, so the published historical results
        cannot change.
      </Bridge>
      <LaneView lane={LANES[1]} />
      <Bridge>
        <strong className="font-medium text-text-secondary">Both paths meet in Hive,</strong> then one export step
        publishes everything to the web app.
      </Bridge>
      <LaneView lane={LANES[2]} />
    </div>
  );
}
