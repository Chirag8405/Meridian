# Architecture diagram

Rendered by GitHub (Mermaid). Source of truth for what each box does is
[ARCHITECTURE.md](ARCHITECTURE.md); the GenAI layer is specified in
[GENAI_ASSISTANT_PLAN.md](GENAI_ASSISTANT_PLAN.md).

```mermaid
flowchart LR
  subgraph SRC["Data sources"]
    DUNE["Dune Analytics<br/>historical backfill (one-time)"]
    ALCH["Alchemy WebSocket<br/>live on-chain swaps"]
  end

  subgraph LOCAL["Local big-data stack (your machine)"]
    direction TB
    HDFS["HDFS + Hive tables<br/>stablecoin_pool_hourly,<br/>risk_scores_baseline"]
    BATCH["Spark / MapReduce batch jobs<br/>baseline stats, K-Means,<br/>PageRank, classifier, risk score"]
    STREAM["Spark Structured Streaming<br/>scores live hours with the<br/>frozen K-Means model"]
    EXPORT["export_dashboard_data.scala<br/>to JSON"]
    ADV["generate_risk_advisories.py<br/>(Groq, best effort)"]
    PUSH["push_to_supabase.py<br/>(every 2 hours, systemd timer)"]
    HDFS --> BATCH --> HDFS
    STREAM --> HDFS
    HDFS --> EXPORT --> ADV --> PUSH
  end

  subgraph CLOUD["Cloud serving"]
    SB[("Supabase Postgres<br/>read-only RLS")]
    API["Render: FastAPI<br/>/api/dashboard-data<br/>/api/recent-swap-*<br/>/api/assistant/chat"]
    WEB["Vercel: Next.js dashboard<br/>Live now, Recent activity,<br/>crisis charts, /assistant"]
    SB --> API --> WEB
  end

  subgraph GENAI["GenAI layer (inside the Render API)"]
    direction TB
    TOOLS["9 read-only tools<br/>(Supabase tables +<br/>BM25 over project docs)"]
    LLM["Groq LLM<br/>tool calling"]
    GROUND["Numeric grounding check,<br/>refusals, rate limits"]
    TOOLS <--> LLM --> GROUND
  end

  EVAL["genai/eval (offline)<br/>frozen snapshot, 80 questions,<br/>advisory + judge experiments"]

  DUNE --> HDFS
  ALCH --> STREAM
  ALCH -. "recent swap events" .-> SB
  PUSH --> SB
  API <--> GENAI
  EVAL -. "measures" .-> GENAI
  WEB -. "browser calls via<br/>Next.js proxy routes" .-> API
```

## Reading the diagram

- **Solid arrows** are data flow in the normal pipeline. **Dotted arrows** are side
  paths: the live feed publishes raw recent swaps straight to Supabase (it does not need
  Hadoop or Spark running), the browser never talks to Render directly (Next.js route
  handlers proxy it), and the evaluation harness measures the assistant offline.
- The dashboard never queries Hive live (a trivial query took 46-56 s on this stack), so
  everything it shows is exported, pushed to Supabase, and served by the Render API.
- The model never produces the risk assessment: the rule-based pipeline computes the score
  and the model only explains and retrieves, with every number in an answer checked against
  the evidence it was given.
