# Data Sources

## Chosen (active)

### Dune Analytics — historical backfill
- **Role:** One-time/periodic historical backfill, not a running process
- **Access method:** Ad-hoc SQL execution via Dune's API
  (`POST /api/v1/sql/execute` against `dex.trades`), polled for completion
  via `GET /api/v1/execution/{id}/results`
- **Auth:** `DUNE_API_KEY` in `.env` — see `.env.example`
- **Cost:** Credit-based. A 5-day, 1-pool hourly-aggregated test pull used
  **0.13 credits** against a 2500-credit billing period allowance (checked
  live via `POST /api/v1/usage`) — effectively free at this project's scale.
  A full 6-month backfill across 3 pool/pair combinations was estimated at
  ~15 credits total (see chat history / commit history around
  `hive/schema.sql` for the full estimate).
- **Rate limits:** None hit in testing. `sql.execute` requires only `Read`
  scope — ad-hoc SQL does **not** require the paid Analyst plan (that's only
  needed for the separate "save a named query" endpoint, which we don't use)
- **Validated:** March 2023 USDC depeg is clearly visible — implied
  USDC/USDT price on Curve 3pool bottomed at $0.8808 at 2023-03-11 07:00 UTC,
  matching the widely-reported ~$0.88 low
- **Script:** `ingestion/dune_test_pull.py`

### Alchemy — live streaming feed
- **Role:** Ongoing live feed, intended to back the Spark Structured
  Streaming component
- **Access method:** WebSocket JSON-RPC pubsub (`eth_subscribe` with a
  `logs` filter) against `wss://eth-mainnet.g.alchemy.com/v2/{key}`, plus
  `eth_call` over the HTTPS endpoint for contract reads (token metadata,
  Curve pool balances)
- **Auth:** `ALCHEMY_API_KEY` in `.env` — see `.env.example`
- **Cost:** Free tier
- **Rate limits:** Free tier `eth_getLogs` (used only for diagnostic
  historical checks, not the live path) is capped at a 10-block range per
  call. The live `eth_subscribe` path used for actual ingestion has no such
  range restriction — it streams events as they occur.
- **Real-world activity note:** Both pools we're watching (Curve 3pool,
  Uniswap V2 USDC/USDT) currently see roughly **1 event every 15-20
  minutes each** in calm conditions (measured by sampling recent blocks) —
  far below their 2023 depeg-era volume. A live test window needs to be at
  least several minutes, ideally 10+, to reliably observe real events.
- **Script:** `ingestion/alchemy_live_feed.py`

## Candidates (not currently used)

### Google BigQuery public Ethereum dataset
- **Dataset:** `bigquery-public-data.crypto_ethereum`
- **Access method:** SQL queries via BigQuery
- **Cost:** Needs a GCP account with billing enabled; free tier query
  allowance available
- **Rate limits:** Governed by GCP free tier query quota
- **Status:** Not needed — Dune covers the same historical need

### CoinGecko / exchange APIs
- **Access method:** REST API
- **Cost:** Free tier available
- **Rate limits:** Free tier request limits apply
- **Notes:** For centralized price feed cross-referencing
- **Status:** Not yet integrated; may be added later for cross-referencing
  DEX-implied prices against centralized exchange prices

## Open Items

- [ ] CoinGecko integration decision (cross-reference vs. skip)
- [ ] Which additional stablecoin pairs/pools beyond the initial
  Curve 3pool + Uniswap V2 USDC/USDT to cover for the full backfill (see
  `SCOPE.md` pending decisions — note this file has moved ahead of that
  one since the source question is now resolved)
