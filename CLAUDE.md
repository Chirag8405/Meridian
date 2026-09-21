# Meridian

## Project Overview

Meridian is a Big Data Analytics mini-project — a DeFi stablecoin depeg and
liquidity-stress early warning system. It ingests on-chain and market data to
detect early signals of stablecoin depeg events (like TerraUSD's May 2022
collapse or USDC's March 2023 SVB-related depeg) before they become visible
on price charts.

## Tech Stack and Exact Versions

- **Hadoop 3.4.3** (HDFS, YARN, MapReduce)
- **Hive 3.1.3** (downgraded from 4.x — Spark 3.5.5 only supports Hive
  metastore versions up to 3.1.x)
- **Spark 3.5.5**
- **Sqoop 1.4.7**
- **MongoDB 8.2.6** (installed via pacman, not yet enabled/running)
- **JDK split (important, not uniform across the stack):**
  - **Hadoop, YARN, and Spark run on JDK 11.**
  - **Hive and Sqoop run on JDK 8** — both hard-crash on JDK 9+ (Hive 3.1.3
    has a `ClassCastException` baked into `SessionState`'s constructor;
    Sqoop 1.4.7 is contemporaneous and shares the same risk). Scoped via
    `hive-env.sh`/`sqoop-env.sh` overriding `JAVA_HOME` for those tools only.
  - Hive's own MapReduce *task containers* also needed to be pinned to JDK 8
    via `mapreduce.map.env`/`mapreduce.reduce.env`/`yarn.app.mapreduce.am.env`
    in `hive-site.xml` — Hadoop's NodeManager spawns task JVMs under its own
    JDK (11) by default, which isn't enough on its own.
  - System-wide default remains **JDK 17** via `archlinux-java` — do not
    change the system default.
- **No HBase, no Zookeeper** for this phase (explicitly descoped — may
  revisit later)
- **No GenAI/generative components yet** — BDA-only for now, GenAI
  integration decision is pending confirmation from a separate course

## Known Integration Fixes Applied

- Hive downgraded 4.x → 3.1.3 for Spark metastore compatibility
- Guava version conflict resolved: Hive bundles an old Guava (22.0/19.0)
  that clashes with Hadoop 3.4.3's Guava (32.0.1-jre); Hive's bundled jar was
  swapped for Hadoop's
- `commons-collections` (old v3 API) added to Hadoop's shared classpath —
  required by Hive-on-MR but not bundled with Hive 4.x/3.1.3
- `commons-cli` conflict resolved for Sqoop: Sqoop 1.4.7's parser needs an
  old API method, Hadoop's `GenericOptionsParser` needs a newer one; pinned
  to commons-cli 1.3.1, the one version with both
- Hive metastore's notification-events API auth disabled
  (`hive.metastore.event.db.notification.api.auth=false`) — it requires
  Hadoop proxyuser config that a single local user doesn't have
- Hive query-results-cache disabled (`hive.query.results.cache.enabled=false`)
  — known Hive 3.1.x NPE bug in `SemanticAnalyzer.checkResultsCache`
- **Confirmed: Hive 3.1.3 does NOT run cleanly on JDK 11** (hard
  `ClassCastException`, not fixable via config) — this is why it runs on
  JDK 8 specifically. See the JDK split above.

## Conventions

- All new Spark/Hive/MapReduce code goes under clearly separated module
  directories (`ingestion/`, `hive/`, `spark/`, `streaming/`, `mllib/`)
- Never modify system-wide `JAVA_HOME` or `archlinux-java` default
- Don't install HBase/Zookeeper without explicit request
- Document any new env var or config file change in `SETUP.md` immediately
- **Launch any Spark/Hive job expected to run more than a couple minutes via
  `nohup` (detached from the tool's own process lifecycle) by default — not
  only after a timeout is hit.** Incident: an `INSERT` rewriting
  `stablecoin_pool_hourly` to a non-ACID table completed its MapReduce stage
  on YARN, but the client session was cut when the shell tool's own timeout
  auto-backgrounded it, so the finalization step (moving staged output into
  partitions, registering them in the metastore) never ran — the job showed
  as "succeeded" while the target table silently stayed empty. Re-running
  the same job via `nohup ... &`, detached from the start, completed
  cleanly. Don't wait for a timeout to make this call.

## Further Reading

Refer to [ARCHITECTURE.md](ARCHITECTURE.md), [LAB_MAPPING.md](LAB_MAPPING.md),
[SCOPE.md](SCOPE.md), [DATA_SOURCES.md](DATA_SOURCES.md),
[ROADMAP.md](ROADMAP.md), and [FINDINGS.md](FINDINGS.md) (genuine
analytical findings from the data, e.g. UST having no reliable baseline —
read before building the risk-scoring model) for full project context
before starting new work.
