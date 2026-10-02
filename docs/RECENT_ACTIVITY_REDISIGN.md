Plan: Interactive Recent Activity Graph
Replace the long raw-event list with an investigative activity surface that answers “what is happening?” without implying risk.

Recommended approach

Use a discrete SVG bar graph for swap counts, with filters and click-to-inspect event details. Keep the raw event list as a secondary detail view.

Steps

Define separate graph API

Keep /api/recent-swap-events for raw event details.
Add /api/recent-swap-activity for aggregated buckets.
Support windows: 15m, 1h, 6h, 24h.
Support filters: pair, pool, and source.
Return bucket start/end, total count, live count, and gap-filled count.
Bucket by observed_at, not event_ts, because this graph describes feed activity.
Return zero-count buckets so quiet periods remain visible.
Implement backend aggregation

Update main.py.
Validate all query parameters.
Query the bounded recent_swap_events retention window.
Apply filters and aggregate in UTC.
Keep the existing 25-row raw-event display limit separate from graph aggregation.
Return honest data boundaries so the graph does not imply coverage beyond the 100-row/48-hour retention policy.
Add frontend data types

Update data.ts.
Add types for activity buckets, filters, and summaries.
Add a separate activity-data getter.
Keep the raw event getter independent.
Preserve the 20-second refresh behavior for live data.
Refactor the Recent activity component

Update RecentActivity.tsx.
Add:
Window controls: 15m, 1h, 6h, 24h
Pair filter
Pool filter
Source filter
Summary row:
Events in selected window
Last observed time
Active pools
Live versus gap-filled count
Replace the default long table with a native SVG bar graph.
Display 10-12 recent raw events below the graph.
Add graph interaction

Use bars, not a smoothed line.
Reuse interaction conventions from CrisisChart.tsx:
Transparent hit layer
Keyboard navigation
role="slider"
aria-live readout
Clicking or focusing a bar selects that time bucket.
Show only events from the selected bucket in the detail list.
Add a reset option to return to all activity.
Add event inspection

Keep the compact row content:
Pool
Pair
Implied price
Observed time
live or gap-filled
Expand a selected row to show:
Transaction hash
Log index
Blockchain event timestamp
Feed-observed timestamp
Pool address
Price
Use tx_hash + log_index as the React key.
Handle honest states

Empty selected window:
“No swaps observed in this window.”
Sparse window:
Show zero buckets and explain that pool activity is intermittent.
Stale data:
Show the age of the latest observed event.
Missing aggregation endpoint during deployment:
Fall back to the existing raw-event empty state for 404.
Preserve untracked pair and gap-filled provenance labels.
Document semantics

Update ARCHITECTURE.md or SETUP.md.
Document:
observed_at versus event_ts
Graph endpoint
Storage retention versus graph/display windows
The fact that activity counts are descriptive, not risk scores
Relevant files

main.py
data.ts
page.tsx
RecentActivity.tsx
CrisisChart.tsx
LivePriceChart.tsx
schema.sql
ARCHITECTURE.md
No ingestion or Supabase schema change is required for the first version. The existing recent_swap_events table already contains everything needed.

Verification

Test all time windows and filters.
Verify zero-filled buckets and UTC boundaries.
Confirm graph totals match filtered retained events.
Test populated, sparse, empty, and stale states.
Test bucket selection, reset, keyboard navigation, and mobile layout.
Run:
python -m py_compile main.py ingestion/alchemy_live_feed.py
npm run lint
./node_modules/.bin/tsc --noEmit
npm run build
git diff --check
Explicit exclusions

The graph will not include risk scores, anomaly flags, severity colors, alert language, causal interpretation, or browser-side WebSocket streaming. It remains a raw activity view separate from the hourly risk section.