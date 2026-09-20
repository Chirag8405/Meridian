# Architecture

Meridian is organized into five layers, from raw data ingestion through to
the user-facing dashboard.

## 1. Data Sources Layer

- On-chain transaction / pool-state data
- Stablecoin price feeds
- Historical depeg incident records (curated)
- Exchange price data

## 2. Data Integration Layer

- Ingestion scripts pulling from chosen on-chain data source(s) — see
  [DATA_SOURCES.md](DATA_SOURCES.md) (source selection pending)
- Sqoop for transferring curated historical incident records from a staging
  relational DB

## 3. Storage Layer

- **HDFS** for raw ingested data
- **Hive** for the structured/partitioned query layer
- **MongoDB** for flexible semi-structured documents (pool-state JSON,
  price API responses)

## 4. Analytics & Management Layer

- **MapReduce** for baseline liquidity/price-deviation statistics
- **Spark** for PageRank-based wallet/pool influence ranking
- **CURE/Canopy clustering** of historical depeg events by stress signature
- **Spark Structured Streaming** for live pool-ratio/price monitoring
- **MLlib** for depeg-risk scoring

## 5. Application Layer

- Dashboard displaying live risk scores per stablecoin

## Workflow Diagram (Description)

```
Data Sources  →  HDFS  →  Hive / MongoDB  →  Spark / MapReduce  →  Dashboard
```

Raw on-chain and market data lands in HDFS (and MongoDB for semi-structured
documents), gets structured and partitioned in Hive, is processed by Spark
and MapReduce jobs for statistics, clustering, ranking, and risk scoring, and
the results surface on a live dashboard.
