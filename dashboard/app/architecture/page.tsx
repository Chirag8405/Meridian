import type { Metadata } from "next";
import SiteNav from "@/components/SiteNav";
import ArchitectureDiagram from "@/components/ArchitectureDiagram";
import TechStackCard from "@/components/TechStackCard";
import { ProcessTag, WhatIsThis } from "@/components/Explain";

export const metadata: Metadata = {
  title: "Architecture · Meridian",
  description: "End-to-end pipeline of the Meridian project: sources, Hadoop/Hive/Spark batch path, streaming path and how data reaches the dashboard.",
};

function Pillar({ name, headline, children }: { name: string; headline: string; children: React.ReactNode }) {
  return (
    <div className="border border-border bg-surface p-4">
      <p className="font-mono text-[10.5px] uppercase tracking-wide text-text-muted">{name}</p>
      <h3 className="font-sans text-[13px] font-semibold text-text-primary mt-0.5 mb-2">{headline}</h3>
      <div className="font-sans text-[12.5px] leading-snug text-text-muted space-y-2">{children}</div>
    </div>
  );
}

export default function ArchitecturePage() {
  return (
    <main>
      <header className="max-w-5xl mx-auto px-5 pt-8 pb-2">
        <div className="flex flex-wrap items-baseline justify-between gap-4">
          <h1 className="font-sans font-semibold text-[20px] tracking-tight text-text-primary">Architecture</h1>
          <SiteNav current="architecture" />
        </div>
        <WhatIsThis className="mt-1">
          The whole pipeline from raw blockchain data to this page: where each dataset comes from, which Hadoop / Hive /
          Spark job transforms it, which model uses it, and how the result reaches the browser.
        </WhatIsThis>
        <div className="mt-3 flex flex-wrap items-center gap-2 font-sans text-[12px] text-text-muted">
          <span className="font-medium text-text-secondary">Key:</span>
          <ProcessTag type="batch" />
          <ProcessTag type="streaming" />
          <ProcessTag type="ml" />
        </div>
      </header>

      <section aria-labelledby="diagram-heading" className="max-w-5xl mx-auto px-5 py-6">
        <h2 id="diagram-heading" className="sr-only">
          Pipeline diagram
        </h2>
        <ArchitectureDiagram />
      </section>

      <section aria-labelledby="read-heading" className="max-w-5xl mx-auto px-5 py-8 border-t border-border">
        <h2 id="read-heading" className="font-sans font-semibold text-[17px] text-text-primary mb-2">
          How to read this
        </h2>
        <p className="font-sans text-[13px] leading-relaxed text-text-muted max-w-2xl">
          Each bordered block is one path through the system, read top to bottom. The numbered rows are stages; each
          row names the technology in small type under its title and says in plain words what it does. The text on
          every arrow says what data travels along it. The{" "}
          <strong className="font-medium text-text-secondary">batch path</strong> (black edge) works on a fixed
          historical dataset, two real depegs, and only changes when somebody re-runs a job. The{" "}
          <strong className="font-medium text-text-secondary">streaming path</strong> (red edge) handles new swaps as
          they arrive. They share the same Hive tables and the same score formula; the only thing handed from batch to
          streaming is a frozen model. The last block shows how both end up in your browser.
        </p>
      </section>

      <section aria-labelledby="bigdata-heading" className="max-w-5xl mx-auto px-5 py-8 border-t border-border">
        <h2 id="bigdata-heading" className="font-sans font-semibold text-[17px] text-text-primary mb-2">
          Why this is Big Data
        </h2>
        <WhatIsThis className="mb-5">
          The three Vs, with the real numbers from this project. The honest summary: the dataset is modest, and the point
          of the project is the distributed architecture and the streaming design built around it.
        </WhatIsThis>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Pillar name="Volume" headline="Large raw data, aggregated to hourly rows">
            <p>
              15,607 hourly (pair, project, hour) rows feed the clustering step (15,603 after dropping 4 undefined
              prices). USDC pairs span December 2022 – May 2023; UST pairs span April – June 2022.
            </p>
            <p>
              A separate raw pull holds about 135K wallet-level trades across the tracked pools, used to build the wallet
              graph for PageRank.
            </p>
            <p>
              Stored in HDFS and queried through Hive tables partitioned by pair and date, on a single machine in
              pseudo-distributed mode.
            </p>
          </Pillar>
          <Pillar name="Velocity" headline="A live stream, processed in micro-batches">
            <p>
              Swaps arrive over an Alchemy WebSocket as they happen. In calm conditions each pool sees roughly one swap
              every 15–20 minutes; during USDC&apos;s March 2023 crisis, hourly trading volume rose to 9.3× its calm
              level.
            </p>
            <p>
              Spark Structured Streaming groups them into 1-hour windows (2-hour watermark, 10-minute trigger). The
              dashboard re-reads the API every 60 seconds and the Recent activity panel every 20 seconds.
            </p>
            <p>
              Hive on MapReduce took 46–56 s for a trivial count, which is why the dashboard reads pre-exported results
              instead of querying Hive.
            </p>
          </Pillar>
          <Pillar name="Variety" headline="Many shapes of data in one pipeline">
            <ul className="list-disc pl-4 space-y-1">
              <li>Relational hourly tables from Dune</li>
              <li>Semi-structured JSON event logs from the blockchain</li>
              <li>A wallet–pool network (graph data) for PageRank</li>
              <li>External USD prices from CoinGecko</li>
              <li>On-chain bytecode checks (eth_getCode) that label addresses</li>
              <li>Project documents retrieved by the grounded assistant</li>
            </ul>
          </Pillar>
        </div>
      </section>

      <TechStackCard />

      <footer className="max-w-5xl mx-auto px-5 py-6 border-t border-border">
        <p className="font-mono text-[11px] text-text-muted">
          Source of truth: docs/ARCHITECTURE.md, hive/*.sql, spark/*.scala, ingestion/*.py, backend/main.py.
        </p>
      </footer>
    </main>
  );
}
