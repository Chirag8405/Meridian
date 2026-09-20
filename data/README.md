# Data Directory

Raw and processed on-chain/market data is **not** committed to this repo —
it's regenerated/fetched via ingestion scripts, not version-controlled.

## Structure

- `data/raw/` — raw pulls from the chosen data source(s), before any
  transformation. See [DATA_SOURCES.md](../DATA_SOURCES.md) for source
  candidates (final choice pending — see [SCOPE.md](../SCOPE.md)).
- `data/processed/` — cleaned/transformed data derived from `data/raw/`,
  ready for loading into HDFS/Hive/MongoDB.

Both directories are gitignored except for a `.gitkeep` placeholder that
keeps the empty folder tracked.

## Regenerating

Once ingestion scripts exist (see [ROADMAP.md](../ROADMAP.md)), this section
will document the exact commands to fetch raw data and produce the processed
outputs. For now, no ingestion pipeline exists yet — this file is a
placeholder for that documentation.
