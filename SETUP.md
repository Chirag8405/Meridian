# Setup Log

A running install log for future sessions. Update this file immediately
whenever an env var or config file changes.

## System

- Arch Linux, 16GB RAM, 16GB swap
- JDK 17 (system default via `archlinux-java`) and JDK 21 already present
  via pacman before this project started
- JDK 11 installed via pacman for Hadoop/YARN/Spark
- JDK 8 installed via pacman (`jdk8-openjdk`) specifically for Hive and
  Sqoop, which do not run on JDK 9+

## Install Paths

All components installed as manual tarballs under `~/bigdata/`, with
version-agnostic symlinks:

| Component | Symlink | Actual Version Dir |
|---|---|---|
| Hadoop | `~/bigdata/hadoop` | `hadoop-3.4.3` |
| Hive | `~/bigdata/hive` | `apache-hive-3.1.3-bin` |
| Spark | `~/bigdata/spark` | `spark-3.5.5-bin-hadoop3` |
| Sqoop | `~/bigdata/sqoop` | `sqoop-1.4.7.bin__hadoop-2.6.0` |

Data directories: `~/bigdata/data/` (HDFS namenode/datanode dirs, Hive
scratch/metastore/log dirs).

## Environment Variables

- Bash-sourceable env file: `~/bigdata/env.sh` (JAVA_HOME=JDK 11,
  HADOOP_HOME, HIVE_HOME, SPARK_HOME, SQOOP_HOME, HADOOP_CONF_DIR, PATH)
- Fish shell: `~/.config/fish/conf.d/bigdata.fish` (same variables, fish
  syntax)
- `~/bigdata/hive/conf/hive-env.sh`: overrides `JAVA_HOME` to JDK 8 for
  Hive's own processes only (metastore, HiveServer2, CLI)
- `~/bigdata/sqoop/conf/sqoop-env.sh`: overrides `JAVA_HOME` to JDK 8 for
  Sqoop, plus `HADOOP_USER_CLASSPATH_FIRST=true` (needed so Sqoop's bundled
  jars take precedence over Hadoop's on the classpath)
- `~/bigdata/hadoop/etc/hadoop/hadoop-env.sh`: `JAVA_HOME` only defaults to
  JDK 11 when not already set, so Hive/Sqoop's JDK 8 override isn't
  clobbered when they invoke `hadoop jar` internally

## Hadoop (pseudo-distributed)

- `core-site.xml`: `fs.defaultFS=hdfs://localhost:9000`
- `hdfs-site.xml`: replication=1, namenode/datanode dirs under
  `~/bigdata/data/hdfs/`, secondary namenode explicitly set to
  `localhost:9868` (avoids trying to SSH to the machine's real hostname)
- `yarn-site.xml`: NodeManager capped at 6GB RAM / 4 vcores (leaves headroom
  on a 16GB dev machine)
- `mapred-site.xml`: framework=yarn
- Verified: HDFS read/write, `hdfs dfsadmin -report`, and a real MapReduce
  job (`yarn jar ... pi`) all working

## Hive

- Downgraded from 4.0.1 to 3.1.3 (see CLAUDE.md for why)
- Metastore: embedded Derby at `~/bigdata/data/hive/metastore_db`, but run
  as a **standalone metastore service** (`hive --service metastore`,
  thrift://localhost:9083) rather than embedded directly in HiveServer2 —
  embedded Derby only allows one JVM to hold the lock at a time, and Spark
  needs to connect too
- HiveServer2 bound to `localhost:10000` only (not `0.0.0.0`)
- `hive.execution.engine=mr` (Tez was never installed; Hive 4.x defaulted to
  Tez and would otherwise loop retrying a Tez session pool at startup)
- Verified via Beeline: CREATE TABLE / INSERT (real MapReduce job) / SELECT

## Spark

- `spark-env.sh`: `SPARK_DIST_CLASSPATH=$(hadoop classpath)` so Spark can
  read/write HDFS
- `spark-defaults.conf`: `spark.sql.hive.metastore.version=3.1.3`,
  `spark.sql.hive.metastore.jars=maven` — Spark's bundled Hive client is
  2.3.x-based and can't speak Hive 4.x's Thrift API at all; even for 3.1.3 it
  needs isolated client jars fetched from Maven at runtime (first run
  downloads them, subsequent runs are cached)
- `~/bigdata/spark/conf/hive-site.xml` kept in sync with Hive's own
  `hive-site.xml` (copy whenever the Hive one changes)
- Verified: local mode, YARN mode, HDFS read/write, and reading a
  Hive-managed table through the metastore — all working

## MongoDB

- 8.2.6, installed via pacman
- `mongodb.service` exists but is **disabled and not running** — not yet
  enabled for this project

## SSH (for Hadoop pseudo-distributed daemon control)

- Dedicated keypair: `~/.ssh/id_hadoop` (separate from the existing GitHub
  key), added to `~/.ssh/authorized_keys`
- `~/.ssh/config` has a `Host localhost` entry using that key
- sshd scoped to localhost only: `/etc/ssh/sshd_config.d/10-hadoop-localhost.conf`
  sets `ListenAddress 127.0.0.1` / `::1` and `PasswordAuthentication no` —
  **not** exposed on any external interface

## Sqoop

- 1.4.7 (last release; project is unmaintained/in the Apache Attic)
- JDBC driver: MariaDB Connector/J 3.3.3 (`~/bigdata/sqoop/lib/`) — Sqoop's
  built-in MySQL manager hardcodes `com.mysql.jdbc.Driver`, which doesn't
  exist without a real MySQL connector, so imports need `--driver
  org.mariadb.jdbc.Driver --connection-manager
  org.apache.sqoop.manager.GenericJdbcManager` and a `jdbc:mariadb://` URL
  (not `jdbc:mysql://`, which Sqoop's manager fails to explicitly load the
  driver for)
- Verified: import from a local MariaDB test table into HDFS via a real
  MapReduce job

## HBase, Zookeeper

- Intentionally not installed (see SCOPE.md)

## Convenience Scripts

- `~/bigdata/start-all.sh`: starts HDFS, YARN, Hive metastore, HiveServer2
- `~/bigdata/stop-all.sh`: stops all of the above
- Spark and Sqoop need no daemon — invoked directly per job/command

## Live streaming (Alchemy feed + Spark Structured Streaming consumer)

- **CoinGecko**: no API key needed. `COINGECKO_API_KEY` stays empty in
  `.env`/`.env.example` — the live feed ingester uses CoinGecko's keyless
  public `/simple/price` endpoint, confirmed sufficient at this call
  volume (a handful of calls/minute against a 5-15 calls/min keyless
  limit). Would only need a key if call volume grows substantially later.
- **Clustering model persistence**: `spark/persist_clustering_model.scala`
  must be run once (already done) before the streaming consumer can start
  — it saves `spark/models/stress_clustering/{scaler,kmeans}` to HDFS
  (not local disk — resolves against Spark's default filesystem). See
  FINDINGS.md's "Guarantee" section for why this exists.
- **systemd `--user` services** (`systemd/*.service` in this repo, copied
  to `~/.config/systemd/user/`):
  ```
  cp systemd/meridian-live-feed.service systemd/meridian-stream-consumer.service \
     ~/.config/systemd/user/
  systemctl --user daemon-reload
  loginctl enable-linger "$(whoami)"   # one-time — services stop on
                                        # logout otherwise (confirmed
                                        # Linger=no by default on this
                                        # machine)
  systemctl --user enable --now meridian-live-feed.service
  # start the streaming consumer only after start-all.sh has HDFS/Hive up —
  # it is not itself managed by systemd, per this project's existing
  # manual-startup convention:
  systemctl --user enable --now meridian-stream-consumer.service
  ```
- Landing directory for decoded events: `data/raw/alchemy_live_stream/`
  (gitignored, local filesystem — read by Spark via an explicit `file://`
  path, since Spark's default filesystem is HDFS, not local disk).
- State file: `data/raw/alchemy_live_stream_state.json` (last-processed
  block number, for gap-fill on reconnect/restart).
- Checkpoint: `spark/checkpoints/stream_alchemy_live/` (HDFS).

## Live backend (Supabase + Render) — replaces static-JSON-at-build-time

Design confirmed before implementing — see ARCHITECTURE.md's Application
Layer section for the full report (data size, auth model, why Server
Component fetch over client-side/proxy, why no fallback yet). This
section is the exact provisioning sequence — **these steps require your
own account access and can't be done by an agent**: creating the Supabase
project, deploying the Render service, and creating the UptimeRobot
monitor all happen in consoles this project has no credentials or browser
access to. Do them in this order — doing them out of order means the
Vercel build fails (see the last bullet for why that's expected, not a bug).

1. **Create the Supabase project** (free tier). In the SQL Editor, run
   `supabase/schema.sql` once — creates the 7 tables + Row Level Security
   policies (public `SELECT` only; writes require the secret key, which
   bypasses RLS).
2. **Collect two keys** from Supabase's API settings: `sb_secret_...`
   (bypasses RLS, full write access) and `sb_publishable_...` (respects
   RLS, read-only in practice given the schema's policies). Confirmed via
   Supabase's own docs that new projects default to this naming as of
   2026, not the legacy `anon`/`service_role` names — both still work
   during Supabase's transition period, but building against the current
   names is the right call.
3. **Local `.env`**: set `SUPABASE_URL` and `SUPABASE_SECRET_KEY` (the
   secret key — this is a write credential, local machine only, never on
   Render or Vercel). Run once to populate initial data:
   ```
   source .venv/bin/activate   # or wherever this project's Python venv lives
   python3 ingestion/push_to_supabase.py
   ```
   Rerun this after every `spark/export_dashboard_data.scala` run — same
   "batch job, rerun by hand" model as the rest of this project. Nothing
   downstream shows anything meaningful until this has run at least once.
4. **Deploy the Render backend**: new Web Service pointed at this repo,
   root directory `backend/`, build command `pip install -r
   requirements.txt`, start command `uvicorn main:app --host 0.0.0.0
   --port $PORT`. Set two environment variables on Render:
   `SUPABASE_URL` and `SUPABASE_PUBLISHABLE_KEY` (the *publishable* key
   here, not the secret one — the backend only ever reads). Confirm
   `https://<your-service>.onrender.com/health` returns
   `{"status":"ok","supabase":"reachable"}` before moving on — this
   endpoint genuinely queries Supabase, not a stub, so a working response
   here means the whole chain (Render ↔ Supabase) is actually verified,
   not just "the process started."
5. **UptimeRobot**: create an HTTP(s) monitor against that `/health` URL,
   5-minute interval, free tier. This is what keeps Render from spinning
   down after 15 minutes idle *and* generates real Supabase traffic that
   keeps its free-tier project from pausing after 7 days of inactivity —
   both rely on `/health` doing a genuine query, confirmed in step 4.
   **Flagging the real cost of this, not hiding it**: Render's free tier
   grants 750 instance-hours/month; staying awake 24/7 this way consumes
   ~720-744 of those hours — fine for a single service with no other
   Render usage on the account, worth knowing if that changes.
6. **Vercel environment variable**: set `RENDER_API_URL` to the Render
   service's base URL (`https://<your-service>.onrender.com`, no trailing
   slash) in Vercel's project settings — **before** triggering a build,
   not after. The dashboard fetches this at build time too, not just at
   runtime (confirmed design: `revalidate: 60` means Next.js performs
   static generation at build time as the initial cache, then revalidates
   in the background after the interval passes — it's not
   `force-dynamic`). A build triggered before Render is live and correctly
   configured will fail cleanly with a clear error naming the missing
   config or unreachable backend, not deploy something broken silently —
   confirmed by testing locally without `RENDER_API_URL` set.
