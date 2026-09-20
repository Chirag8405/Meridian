# Data Sources

> **Status: pending final decision.** This file lists candidates only. Fill
> in the final choice, actual endpoints, and API key setup once a source is
> selected — see the pending decisions in [SCOPE.md](SCOPE.md).

## Candidates

### Google BigQuery public Ethereum dataset
- **Dataset:** `bigquery-public-data.crypto_ethereum`
- **Access method:** SQL queries via BigQuery
- **Cost:** Needs a GCP account with billing enabled; free tier query
  allowance available
- **Rate limits:** Governed by GCP free tier query quota

### Dune Analytics
- **Access method:** Pre-aggregated queries via Dune's query engine/API
- **Cost:** Free tier available
- **Rate limits:** Free tier query limits apply
- **Notes:** Good for pre-aggregated DEX/lending protocol data

### Direct RPC via Infura or Alchemy
- **Access method:** Direct JSON-RPC calls to an Ethereum node provider
- **Cost:** Free tier available
- **Rate limits:** Free tier request limits apply
- **Notes:** Needed for true real-time streaming

### CoinGecko / exchange APIs
- **Access method:** REST API
- **Cost:** Free tier available
- **Rate limits:** Free tier request limits apply
- **Notes:** For centralized price feed cross-referencing

## To Be Filled In

- [ ] Final source decision
- [ ] Actual endpoints
- [ ] API key setup instructions
