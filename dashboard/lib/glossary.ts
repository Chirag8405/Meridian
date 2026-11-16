// Glossary + tech-stack content for the explanation layer. General terms are
// defined in plain language; every project-specific statement comes from the
// repo (docs/ARCHITECTURE.md, docs/FINDINGS.md, spark/*, ingestion/*).

export type GlossaryEntry = { term: string; def: string };

export const GLOSSARY: GlossaryEntry[] = [
  { term: "Stablecoin", def: "A cryptocurrency designed to always be worth $1, such as USDC, USDT, DAI or TerraUSD (UST)." },
  { term: "Depeg", def: "When a stablecoin stops trading at about $1. USDC fell to $0.8808 in March 2023; UST fell to $0.0334 in May 2022." },
  { term: "On-chain swap", def: "A trade of one token for another executed by a smart contract on the Ethereum blockchain, recorded publicly with a transaction hash." },
  { term: "Liquidity pool", def: "A smart contract holding two or more tokens that anyone can trade against. A lopsided pool is an early sign of stress." },
  { term: "Curve 3pool", def: "One Curve pool holding DAI, USDC and USDT together. One contract covers both USDC_DAI and USDC_USDT in this project." },
  { term: "Uniswap V2", def: "A pool type for exactly two tokens. This project tracks the USDC/USDT and USDC/DAI Uniswap V2 pools." },
  { term: "Implied price", def: "The price worked out from a swap: tokens received ÷ tokens sent. About 1.00 when two stablecoins trade one-for-one." },
  { term: "Hourly window", def: "All swaps in one clock hour for one pool, rolled into a single row (trade count, volume, average implied price)." },
  { term: "Baseline", def: "What \"calm\" looks like for a pair: mean and standard deviation of price, volume and trade count in a quiet period." },
  { term: "Standard deviation (σ)", def: "A measure of normal wobble. \"−3σ\" means three times further from the average than the usual day-to-day variation." },
  { term: "Risk score", def: "The project's 0–100 stress number: 40% price, 25% volume and trades, 15% K-Means cluster, 20% wallet concentration." },
  { term: "K-Means", def: "A clustering algorithm that groups similar hours together. Here it forms 4 groups of stress patterns (k = 4)." },
  { term: "Cluster severity", def: "A 0–1 number for how bad an hour's K-Means group is: 0.05 calm, 0.5 moderate, 0.85 severe, 1.0 for UST's zero-value trades." },
  { term: "Frozen model", def: "A model that is saved and only applied to new data, never re-trained, so already-published results cannot silently change." },
  { term: "PageRank", def: "An algorithm that ranks nodes in a network by how much flow passes through them. Google originally used it for web pages; here it ranks wallets and pools." },
  { term: "EOA vs contract", def: "An EOA (externally owned account) is a normal wallet controlled by a person. A contract is code, such as a router or aggregator." },
  { term: "Precision", def: "Of the hours flagged as crisis, the share that really were crisis. High precision means few false alarms." },
  { term: "Recall", def: "Of the real crisis hours, the share that were caught. High recall means few misses." },
  { term: "F1", def: "A single score balancing precision and recall (their harmonic mean). 1.0 is perfect." },
  { term: "PR-AUC", def: "The area under the precision–recall curve: how well the model does across all possible alert thresholds. 1.0 is perfect." },
  { term: "Lead time", def: "The hours between the score's first sustained alarm and the visible depeg. USDC: 72 hours. UST: 0, because its data starts already elevated." },
  { term: "Hadoop (HDFS, YARN)", def: "HDFS stores big files across disks or machines; YARN schedules the jobs that run on them. Here it runs on one machine in pseudo-distributed mode." },
  { term: "Hive", def: "Lets you query files in HDFS with SQL tables. Here its tables are stored as ORC and partitioned by pair and date." },
  { term: "Spark", def: "A fast engine for large-scale data processing, used here for the statistics, K-Means, PageRank, classifier and the streaming job." },
  { term: "Structured Streaming", def: "Spark's way of processing a continuous flow of data in small batches. Here: 1-hour windows, a 2-hour watermark and a 10-minute trigger." },
  { term: "WebSocket", def: "A connection that stays open so a server can push events the moment they happen. The live feed uses one to Alchemy's Ethereum node." },
  { term: "Gap-filled", def: "Events recovered with an eth_getLogs query after the live connection missed some blocks. Real data, delivered late." },
  { term: "Leave-one-coin-out", def: "Train on one coin's crisis and test on the other, which the model has never seen." },
];

export type TechRow = { tech: string; role: string };

export const TECH_STACK: TechRow[] = [
  { tech: "Dune Analytics", role: "Historical backfill: hourly swap aggregates and ~135K wallet-level trades (one-time SQL pulls)." },
  { tech: "Alchemy WebSocket (Ethereum)", role: "Live swap events from 4 pools, with eth_getLogs gap-fill after disconnects." },
  { tech: "Hadoop 3.4.3 (HDFS, YARN)", role: "Storage and job scheduling, pseudo-distributed on one machine." },
  { tech: "Hive 3.1.3", role: "SQL tables over HDFS (meridian.* schema); runs on MapReduce." },
  { tech: "Spark 3.5.5", role: "All batch jobs, MLlib models, GraphX PageRank and the Structured Streaming consumer." },
  { tech: "Sqoop 1.4.7", role: "Documented route for importing curated incident records from a relational staging database." },
  { tech: "MLlib", role: "K-Means (k = 4), logistic regression and random forest." },
  { tech: "GraphX", role: "Weighted PageRank on the wallet–pool graph." },
  { tech: "Supabase (Postgres)", role: "Hosts the exported results and recent swap events for the web app." },
  { tech: "FastAPI on Render", role: "Read-only API that serves Supabase data to the dashboard." },
  { tech: "Next.js on Vercel", role: "This dashboard; Server Components fetch the API every 60 seconds." },
  { tech: "Groq", role: "Writes the plain-English risk advisories and powers the grounded assistant." },
];
