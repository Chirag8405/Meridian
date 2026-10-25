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
  to `~/.config/systemd/user/`). The Hadoop/Hive stack is now also managed by
  `meridian-hadoop-stack.service`; it starts HDFS, waits for HDFS readiness,
  starts YARN, waits for the ResourceManager and NodeManager, then starts the
  Hive metastore and HiveServer2 and verifies a real Hive query before the
  dependent services are released:
  ```
  cp systemd/meridian-live-feed.service systemd/meridian-hadoop-stack.service \
     systemd/meridian-stream-consumer.service \
     systemd/meridian-dashboard-publish.service \
     systemd/meridian-dashboard-publish.timer \
     ~/.config/systemd/user/
  systemctl --user daemon-reload
  loginctl enable-linger "$(whoami)"   # one-time — services stop on
                                        # logout otherwise (confirmed
                                        # Linger=no by default on this
                                        # machine)
  systemctl --user enable --now meridian-live-feed.service
  systemctl --user enable --now meridian-hadoop-stack.service
  systemctl --user enable --now meridian-stream-consumer.service
  systemctl --user enable meridian-dashboard-publish.service
  systemctl --user enable --now meridian-dashboard-publish.timer
  ```
- The dashboard publisher timer runs every two hours and also has a calendar
  trigger so `Persistent=true` can catch up a missed run after boot or wake.
  The publisher waits for a queryable Hive service, takes an `flock`, runs the
  Spark export, and only then pushes the complete export to Supabase.
- Landing directory for decoded events: `data/raw/alchemy_live_stream/`
  (gitignored, local filesystem — read by Spark via an explicit `file://`
  path, since Spark's default filesystem is HDFS, not local disk).
- State file: `data/raw/alchemy_live_stream_state.json` (last-processed
  block number, for gap-fill on reconnect/restart).
- Checkpoint: `spark/checkpoints/stream_alchemy_live/` (HDFS).

### Lightweight live activity mode

The live Alchemy feed does not require Hadoop, Hive, or Spark. To collect raw
live events and publish the Recent activity data while keeping the Java stack
off, first stop the systemd copy of the feed and run the foreground launcher:

```bash
systemctl --user stop meridian-live-feed.service
./ingestion/start_live_activity.sh
```

The launcher runs `ingestion/alchemy_live_feed.py` directly. It writes decoded
events to `data/raw/alchemy_live_stream/` and publishes SWAP events to
Supabase. Press `Ctrl+C` to stop live collection; no Hadoop/Hive/Spark
processes are started. Do not run this alongside
`meridian-live-feed.service`, because both processes share the Alchemy stream
state file and landing directory.

### Manual local batch pipeline

For a lab-friendly workflow, the heavy Java stack does not need to run all the
time. Keep the lightweight live launcher running only when you want to collect
new events, then run the finite batch pipeline manually when you want to
process and publish them:

To switch away from the always-on systemd mode first:

```bash
systemctl --user disable --now meridian-live-feed.service
systemctl --user disable --now meridian-stream-consumer.service
systemctl --user disable --now meridian-dashboard-publish.timer
systemctl --user stop meridian-hadoop-stack.service
```

```bash
./ingestion/run_local_pipeline.sh
```

The script starts the user-managed HDFS/YARN/Hive stack if it is not already
running, runs the Spark live job in `AvailableNow` batch mode so it processes
currently landed files and exits, exports the dashboard data, pushes it to
Supabase, and stops the heavy stack if this script started it. It uses the
existing Spark checkpoint, so already-consumed landing files are not processed
again. It refuses to run while the infinite
`meridian-stream-consumer.service` is active, preventing two Spark consumers
from sharing the same checkpoint.

The two manual processes are therefore independent:

```bash
# Terminal 1: collect live raw events; Ctrl+C stops collection
./ingestion/start_live_activity.sh

# Terminal 2, whenever you want to process/publish accumulated data
./ingestion/run_local_pipeline.sh
```

The batch script is intentionally local-only. It does not deploy a producer
to Render/Vercel; the deployed dashboard reads whatever the local feed has
published to Supabase.

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
  Set `GROQ_API_KEY` in the same local `.env` to enable the best-effort
  advisory step in `systemd/publish-dashboard.sh`; it is never configured
  on Render or exposed to the dashboard. If it is absent or a Groq request
  fails, the risk scores still publish and the advisory field remains null.
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


## Grounded assistant (backend/assistant)

Plan and rationale: `docs/GENAI_ASSISTANT_PLAN.md`. Endpoint:
`POST /api/assistant/chat` on the Render service (body `{"question": str, "history": []}`).

Render environment variables (Render dashboard -> Meridian -> Environment):

| Variable | Required | Default | Meaning |
|---|---|---|---|
| `GROQ_API_KEY` | yes | none | Secret. Without it the endpoint answers HTTP 503 "assistant unavailable"; the rest of the API is unaffected. |
| `ASSISTANT_MODEL` | no | `openai/gpt-oss-20b` | Groq model id (must support tool calling). |
| `ASSISTANT_PER_IP_PER_MIN` | no | `3` | Questions per client per minute. |
| `ASSISTANT_GLOBAL_PER_MIN` | no | `3` | Questions per minute across everyone (Groq's 8,000 tokens/minute limit). |
| `ASSISTANT_PROXY_SECRET` | recommended | empty | Shared secret. When set, the backend only trusts the forwarded visitor address (`x-client-ip`) if the request also carries a matching `x-proxy-secret`; set the SAME value as a Vercel environment variable so the Next.js proxy sends it. Without it, anyone calling Render directly can forge addresses and sidestep the per-visitor limit (the global and daily caps still hold). |
| `ASSISTANT_DAILY_CAP` | no | `200` | Questions per UTC day (Groq's limit is 1,000 requests/day; a question uses up to ~4). |

Limits are in memory (single Render instance; reset on restart). The Next.js
proxy forwards the visitor address as `x-client-ip` (plus `x-proxy-secret`, see
above). Requests larger than 8 KB or without a Content-Length are rejected before
parsing.

The retrieval corpus is committed at `backend/assistant/corpus.json` because
Render deploys only `backend/`. Rebuild it after editing FINDINGS.md,
ARCHITECTURE.md, SCOPE.md or DATA_SOURCES.md:

```
python genai/build_corpus.py          # rewrite the corpus
python genai/build_corpus.py --check  # fails if it is stale
```

Tests: `cd backend && pip install -r requirements.txt -r requirements-dev.txt && pytest tests -q`.


### Running the GenAI evaluation (genai/eval)

Offline, never part of the request path. Needs `GROQ_API_KEY` in the local `.env`
and a Python with `httpx`, `requests`, `fastapi`, `pytest` (for example
`pip install -r backend/requirements.txt -r backend/requirements-dev.txt requests`).
It spends real Groq quota (1,000 requests/day and 8,000 tokens/minute on this key):
about 33 + 47 questions at ~3K tokens each, plus 100 advisories per model.

```
python genai/eval/run.py snapshot            # freeze live data (read-only calls to the Render API)
python genai/eval/run.py questions           # rebuild questions.json; gold is computed from the snapshot
python genai/eval/run.py chat --split dev    # tuning set
python genai/eval/run.py chat --split test   # frozen set: final numbers only
python genai/eval/run.py advisory            # B1, 3 models x 100 synthetic rows
python genai/eval/run.py mutation            # B3, offline
python genai/eval/run.py report              # writes genai/eval/results/REPORT.md
pytest genai/eval/test_eval_units.py         # scoring-code unit tests, no network
```
Runs resume from `genai/eval/results/*.json`; delete a record (or pass `--force`) to redo it.

### LLM-judge experiment (Part C) preparation

```
# 1. export the two historical hourly series with rule scores from Hive (long: detach it)
source /home/chirag/bigdata/env.sh
nohup timeout 1h $SPARK_HOME/bin/spark-shell -i spark/export_judge_series.scala > /tmp/judge_export.log 2>&1 &
# 2. build anonymised 24h windows, labels, and the non-LLM predictors (no API calls)
python genai/eval/run.py judge-windows
python genai/eval/run.py judge --score       # rule / price-alarm / majority results only
# 3. run the LLM judge (spends Groq quota: ~1.2K tokens per window, ~75 USDC + 23 UST windows)
python genai/eval/run.py judge --model openai/gpt-oss-120b
```
`genai/eval/judge/windows.json` is derived and git-ignored; `series_*.json` are committed.


## Auto-commit of exported dashboard data

`dashboard/data/*.json` is regenerated by the publish job every two hours. A second systemd `--user`
job commits those files to `origin/main` so they stop piling up as uncommitted changes:

- `systemd/autocommit-dashboard-data.sh`, run by `meridian-data-autocommit.service`, triggered (a) right after
  every successful `meridian-dashboard-publish.service` (`OnSuccess=`) and (b) by `meridian-data-autocommit.timer`
  every 20 minutes (first run 3 minutes after login/boot), which also catches exports made while offline.
- It commits **only** `dashboard/data/*.json`, from its own git worktree
  (`~/.local/share/meridian-autocommit/worktree`, reset to `origin/main` on each run), so it never touches your
  working copy, branch, staged files or other edits. It skips while the publish job is running, when `origin` is
  unreachable (offline), and when nothing changed. It never force-pushes.
- If you are on `main`, behind `origin/main` only by its commit(s), and the only uncommitted tracked changes are
  `dashboard/data` files, it fast-forwards your local `main` (otherwise `git pull` aborts, because your working
  files hold the same data as uncommitted modifications). On any other branch your working copy is left alone.
- Install (once; re-run after editing the unit files):
  ```
  cp systemd/meridian-data-autocommit.service systemd/meridian-data-autocommit.timer systemd/meridian-dashboard-publish.service ~/.config/systemd/user/
  systemctl --user daemon-reload && systemctl --user enable --now meridian-data-autocommit.timer
  ```
- Check: `systemctl --user list-timers | grep autocommit`, `journalctl --user -u meridian-data-autocommit -n 20`.
- Stop it: `systemctl --user disable --now meridian-data-autocommit.timer` (the `OnSuccess=` hook then still runs it
  after each publish; remove that line from the publish unit as well to stop completely).
- **Side effect to know about (verified with two test commits):** each commit to `main` triggers a **Vercel**
  deploy (a harmless rebuild every two hours; the live data comes from Render, not from the build). It does **not**
  trigger a Render deploy, because the Render service's root directory is `backend/` and these commits only touch
  `dashboard/data`. To stop the Vercel rebuilds, set an Ignored Build Step in the Vercel project settings
  (for example `git diff --quiet HEAD^ HEAD -- . ':!data'` run from the dashboard root).


## Continuous integration (GitHub Actions)

`.github/workflows/ci.yml` runs on pull requests and on pushes to `main` (pushes that only change
`dashboard/data/**`, i.e. the auto-commit job's, are skipped). Four jobs run in parallel, all offline and
secret-free; `CI passed` is the aggregate status:

| Job | Checks |
|---|---|
| backend | `py_compile` of backend, ingestion and genai Python; `pytest backend/tests`; `pytest genai/eval` (Python 3.14, as on Render) |
| corpus-fresh | `python genai/build_corpus.py --check` (the assistant's committed search corpus matches the docs) |
| dashboard | `npm ci`, `eslint`, `next typegen` (Next 16's generated global types), `tsc --noEmit` (Node 24) |
| hygiene | `git diff --check` for the PR's changes; `bash -n` on every `*.sh` |

Not in CI on purpose: `next build` (fetches live data from Render at build time and would fail whenever Render
sleeps), anything using `GROQ_API_KEY` (the LLM evaluation is run by hand), and the Spark/Hive jobs (they need the
local Hadoop stack). Actions are pinned to commit SHAs. Run the same checks locally:
`pip install -r backend/requirements.txt -r backend/requirements-dev.txt requests`, then the commands in the table.
Branch protection (requiring `CI passed`) is not enabled; if you enable it, allow the auto-commit job's pushes to
`main` to bypass it, or it will be rejected.
