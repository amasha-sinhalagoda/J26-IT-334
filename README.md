# J26-IT-334
Research project repository for J26-IT-334, containing research documentation, datasets, source code, system development resources, and project-related materials.

## Dual-route dataset preprocessing

The routing prototype inputs are stored in `Dual route optimization/`. Run
`python scripts/preprocess_dual_route_data.py` to validate and standardize the
eight workbook tables. Cleaned CSVs and a provenance/limitations report are
written to `processed_data/dual_route/`; source workbooks are not modified.

The preprocessing checks required columns, district names, identifiers,
coordinates, dates, severity/class/status values, scenario references, and
declared geometry types/CRSs. It preserves WKT geometries in EPSG:5234 and
point coordinates in WGS84. All supplied records are retained as prototype
inputs; `accepted_for_prototype` records that choice. The separate
`source_type`/`is_synthetic` columns preserve the provenance stated in the
workbook notes and do not filter records.

It also writes five requested district boundaries to
`processed_data/dual_route/district_boundaries.geojson` and copies the Nuwara
Eliya NBRI LHMP shapefile bundle to
`processed_data/dual_route/nuwara_eliya_lhmp/`. The Geofabrik extract and
geoBoundaries source details are recorded in
`Dual route optimization/source_data/README.md`.

This is a tabular validation/export step, not geometric topology validation.
PostGIS loading and spatial edge matching are subsequent routing steps.

### Build the five-district OSM road graph

Use Python 3.10 or newer, install the routing dependencies, then build from the
dated local Geofabrik extract:

```powershell
py -3.13 -m pip install -r requirements-routing.txt
py -3.13 scripts/build_road_graph.py
```

The builder writes a directed OSMnx GraphML graph and a GeoPackage containing
road edges, nodes, and the five district boundaries under
`processed_data/dual_route/road_graph/`. The graph is projected to EPSG:5234
and includes a 1 km buffer around target districts to retain nearby connector
roads. Each directed edge has a deterministic ID derived from its OSM nodes,
edge key, and OSM way ID(s). Graph direction encodes OSM one-way restrictions;
the `oneway` field is normalized to Boolean for GraphML compatibility, while
`oneway_osm` preserves the raw tag.

OSM maxspeed tags are used when available. Edges without a usable tag use
explicit prototype speeds by highway class in `scripts/build_road_graph.py`;
these are not calibrated Sri Lankan travel speeds, so travel-time outputs are
provisional. The graph manifest records the PBF SHA-256, library versions,
CRS, buffer, and edge/node counts. The Geofabrik source extract is excluded
from Git; its download URL and checksum are documented under
`Dual route optimization/source_data/`. The large generated GraphML and
GeoPackage files are also ignored by Git.

### Crosswalk OSM road references to RDA routes

After building the road graph, run:

```powershell
py -3.13 scripts/build_rda_crosswalk.py
```

The script writes `rda_crosswalk.csv`, a review report, and annotated GraphML
and GeoPackage copies in the road-graph output folder. Direct canonical matches
preserve the RDA route code, class, subclass, and road name on each edge. Plain
OSM references such as `A1` are left unmatched when they could refer to more
than one RDA `AA`/`AB`/`AC` code; candidate codes are listed for manual review.
References with no unambiguous code match are also retained and marked, never
silently assigned to a nearby RDA route.

RDA route class/subclass is road-priority metadata only. It must not be used
as hazard evidence or override a hard-blocked edge.

### Load the graph and routing inputs into local PostGIS

The local PostGIS scripts expect portable PostgreSQL 17 and PostGIS 3.6
archives to be extracted under `%LOCALAPPDATA%\J26-IT-334\` as
`postgresql17\pgsql` and `postgis-stage\postgis-bundle-pg17-3.6.2x64`.
They initialize a user-owned cluster (no Windows service or administrator
rights), listening only on loopback port `55432`. Its `trust` authentication
is for local development only; do not expose this database to a network.

Run these commands once in PowerShell to initialize and start the local
database, then create the database:

```powershell
py -3.13 -m pip install -r requirements-routing.txt
.\scripts\setup_local_postgis.ps1
.\scripts\start_local_postgis.ps1
$psql = Join-Path $env:LOCALAPPDATA 'J26-IT-334\postgresql17\pgsql\bin\psql.exe'
& $psql -h 127.0.0.1 -p 55432 -U dual_route -d postgres -c 'CREATE DATABASE dual_route;'
```

Load the prepared inputs and stop the local server when finished:

```powershell
py -3.13 scripts/load_routing_data_postgis.py
.\scripts\stop_local_postgis.ps1
```

The loader stages and validates a complete schema before publishing it as
`dual_route`; repeat an existing load with
`py -3.13 scripts/load_routing_data_postgis.py --replace`. It creates
`postgis` and loads road edges/nodes, district boundaries, the RDA crosswalk,
and all eight prepared routing tables. Point data are transformed from WGS84
to EPSG:5234. The four-district workbook LHMP zones are combined with the
Nuwara Eliya shapefile, preserving source/provenance fields and its original
`Range` value (including class 100, which is not reinterpreted). Spatial
tables receive GiST indexes and all tables receive primary keys. A row-count,
PostGIS-version, and SRID report is written to
`processed_data/dual_route/postgis_load_report.json`.

This step only stores prepared inputs; it does not match hazards or closures
to road edges, calculate edge status, or create routes. Those are subsequent
implementation steps.

### Match hazards and closures to road edges

With local PostGIS running, build the edge overlays:

```powershell
py -3.13 scripts/build_edge_hazard_status.py
```

The builder writes auditable spatial-match tables and the
`dual_route.edge_scenario_status` view:

- `edge_hazard_matches`: exact edge intersections with flood and landslide
  polygons, retaining event, scenario, validity, and provenance fields.
- `edge_closure_matches`: exact edge intersections with road/bridge closure
  geometries, retaining closed, restricted, and reopened observations.
- `closure_nearest_edge`: nearest-edge diagnostics for every closure geometry.
  Unmatched closures are not silently snapped or used to block a route; the
  nearest edge and distance are provided for review.
- `edge_lhmp_matches`: edge intersections with LHMP polygons. Only classes 3
  and 4 are eligible for the high-hazard soft-penalty signal; source class 100
  remains unchanged and is not treated as class 3 or 4.
- `incident_edge_matches`: every incident snapped to its nearest directed
  edge, with distance recorded and a 50 m eligibility flag. Only records whose
  nearest-edge distance is at most 50 m contribute to the incident signal.
- `edge_static_risk`: per-edge high-LHMP overlap and incident counts/density.
- `edge_scenario_status`: an explicit row per directed edge and scenario.
  Flood/landslide intersections and active `closed` closures are hard blocks;
  high LHMP overlap and nearby incidents are soft signals. Active `restricted`
  closures are exposed separately and also receive the soft tier. RDA fields
  remain metadata and do not affect hazard classification.

“Active” here means the observation window overlaps any part of the scenario
event window. The view is therefore conservative for a scenario, not an
as-of-time operational closure service. Closures are hard-block evidence only
when their line geometry intersects a directed road edge; nearby unmatched
closures are reported as candidates but require review. The supplied
closure/hazard data also retain their declared provenance and are not
represented as independently verified real-world closures. Use `--replace` to
rebuild existing overlays. The build writes match counts and per-scenario tier counts to
`processed_data/dual_route/edge_hazard_status_report.json`. This step does not
implement route selection, risk weights, dispatch/evacuation routers, or an
API. The report also shows which hazard polygons, incident records, closures,
and evacuation origins are actually linked to each scenario; missing links
are left missing rather than inferred.

### Rescue dispatch routing (Task 1)

With local PostGIS running and edge overlays built, route a specified DDMC
station or hospital to a linked incident:

```powershell
py -3.13 scripts/route_rescue_dispatch.py `
  --facility-id FAC-RTN-D01 `
  --incident-record-id RTN220012-01
```

The incident's event determines the scenario. The router builds a directed
road graph for that scenario, removes all `hard_blocked` edges, and minimizes
the sum of remaining edge `travel_time` values. OSM one-way direction is
preserved; parallel edges use the faster available directed edge. Soft risk
signals do not affect rescue travel-time cost. It returns edge/node IDs,
network distance and time, endpoint snap distances, and WGS84 GeoJSON. If no
safe path exists, or if an endpoint is over 1 km from the road-node network,
the result is explicitly `infeasible`. An incident within 50 m of a
hard-blocked nearest road edge is also infeasible. The 1 km endpoint limit is
a prototype guard, and the reported network travel time excludes travel from
the facility/incident point to the snapped graph node.

The route uses the full event-window scenario status (not live, as-of-time
conditions). Facility `operational` and `limited` records can be selected;
their status is returned for dispatchers. For example, save JSON output with
`--output processed_data/dual_route/routes/rescue.json`.

### Capacity-aware evacuation routing (Task 2)

With local PostGIS running and edge overlays built, plan all evacuation
origins in a scenario:

```powershell
py -3.13 scripts/route_evacuation.py --scenario-id SC-RTN-F1
```

The planner removes hard-blocked roads, preserves one-way edge direction, and
computes routes to open shelters with positive `available_capacity`. It
minimizes total assigned person-cost while maximizing the number of known
people served, using a capacity-constrained min-cost flow assignment; an
origin may be split across shelters when that is needed to fit capacity. Each
assignment includes edge/node IDs, route GeoJSON, unweighted travel time,
distance, shelter, allocated people, and generalized route cost. Shelter
capacity is read but never modified; this is a plan preview, not a reservation.
SciPy sparse directed shortest paths are used to reuse each origin's route
search across all candidate shelters.

The per-edge risk score is an explicitly uncalibrated prototype value in
`[0,1]`: the maximum of normalized LHMP risk (class 3 = 0.75, class 4 = 1),
normalized historical incident density
(`min(incidents within 50 m per km / 5, 1)`), and restricted-closure risk
(0.5). Edge cost is `travel_time_seconds * (1 + risk_score)`. This maximum
combination avoids summing correlated signals. Class 100 and other LHMP
classes are not treated as class 3 or 4. Hard-block evidence is never
overridden by soft risk.

Origins whose `affected_people` is missing are left explicitly infeasible;
the planner does not guess people counts from `at_risk_units` or the number
of origin rows. This affects all 507 Nuwara Eliya Ditwah origins in the
current input. Endpoint snaps over 1 km, origins next to a hard-blocked
nearest edge, unreachable origins, and inadequate reachable capacity are
reported rather than given an unsafe route. The plan uses the full
scenario-event-window status, not live as-of-time conditions. Save a result
with `--output processed_data/dual_route/routes/evacuation.json`.

### Ditwah scenario replay inputs (validation Task 1)

Prepare a provenance-preserving replay bundle from the supplied event-linked
records:

```powershell
py -3.13 scripts/prepare_ditwah_replay.py
```

The bundle is written to
`processed_data/dual_route/scenarios/ditwah_replay.json`. Only records explicitly
linked to `EV-NWE-DIT` or `SC-NWE-DIT` are included as event evidence. Nuwara
Eliya incidents within the seven days before the event are listed separately
as contextual history, not as confirmed Ditwah failures or road closures.
The output also carries all linked HR origins and readiness blockers. It does
not copy footprints from another event, generate synthetic closures, or infer
affected-person counts. A ready result requires event-linked hazard footprints
and known origin demand; route evaluation is a separate next task.

### Evaluate the Ditwah replay (validation Task 2)

Run the planner and produce a metric-readiness report:

```powershell
py -3.13 scripts/evaluate_ditwah_replay.py
```

The command writes `ditwah_evacuation.json` and `ditwah_evaluation.json` under
`processed_data/dual_route/`. It records planner latency, origin outcomes, and
which metrics can be evaluated. A short-circuited request with no known demand
is not counted as a full routing-latency result. Route-safety, baseline-detour,
and sensitivity metrics remain explicitly `not_evaluable` unless event-linked
hard-hazard evidence, usable origin demand, and route results are available.
An empty route set is never reported as 100% safe.

### Routing API (integration Task 1)

Install routing/API dependencies and start the local API bound to loopback:

```powershell
py -3.13 -m pip install -r requirements-routing.txt
py -3.13 -m uvicorn scripts.routing_api:app --host 127.0.0.1 --port 8000
```

`POST /route` accepts either a rescue-dispatch request with
`mode`, `facility_id`, and `incident_record_id`, or an evacuation request with
`mode` and `scenario_id`. Both accept an optional `alert_id` for traceability.
For example:

```json
{
  "mode": "rescue_dispatch",
  "alert_id": "MOCK-ALERT-001",
  "facility_id": "FAC-RTN-D01",
  "incident_record_id": "RTN220012-01"
}
```

The endpoint calls the existing PostGIS-backed routers and returns their route
result, including GeoJSON geometry where a route exists. Input/domain errors
return HTTP 422 and database failures return HTTP 503; no unsafe fallback
route is generated. Bind to loopback for local prototype use; authentication,
external alert ingestion, are not implemented.

The MapLibre client is available at `http://127.0.0.1:8000/map`. It renders
feasible route GeoJSON and origin/destination markers returned by the API;
evacuation assignments appear as separate route lines. OpenStreetMap tiles
and the MapLibre browser library are loaded from public services, so mapping
requires browser network access. Attribution is displayed in the map.

The same page also includes the **Resource dispatch** view. It calculates a
read-only preview from prepared allocation CSVs, the current workbook inventory
snapshot, and the local reservation ledger. The map shows alert locations and
assigned resource locations; straight-line proximity estimates are labeled as
such and are not drawn as road routes. The UI does not dispatch resources or
reserve inventory. Both views use a dark, map-led layout and are available at
`http://127.0.0.1:8000/map` after starting the API above. The dispatch preview
endpoint does not require PostGIS; rescue and evacuation routing still require
the local routing database.

Run the mock alert contract tests with:

```powershell
py -3.13 -m unittest tests.test_routing_api
```

## Resource allocation input preparation

Run `preprocess_dispatch.py`, then `build_alert_priorities.py`, then
`scripts/prepare_allocation_inputs.py` to prepare allocation requests,
compatible resource candidates, and `processed_data/allocation/district_resource_scarcity.csv`.

The local scarcity score is calculated per district and resource type as
`max(local demand - local available supply, 0) / local demand`. It ranges from
0 (local supply covers demand) to 1 (no local supply). Cross-district inventory
is excluded from this diagnostic. The score is included on each prepared request
and candidate. The optimizer combines it with alert priority as
`0.80 * alert priority score + 0.20 * local scarcity score` when ranking
allocations. This is a documented prototype weighting, not a calibrated
operational policy.

## Validate and reserve a dispatch plan

Run `scripts/run_allocation_solver.py` for a **preview**. It reads the current
`Resource_Inventory_5Districts.xlsx` availability, subtracts existing
reservations, solves the remaining requests, validates the plan, and writes the
results under `processed_data/allocation/results/`. Preview mode does not write
the reservation ledger.

After reviewing the generated plan, run `scripts/run_allocation_solver.py
--approve` to persist its allocated quantities in
`processed_data/allocation/reservations.csv`. Future runs subtract those
quantities from both the matching request and resource availability; over-
reservation is rejected. The ledger is the prototype's reservation record:
the workbook is not edited and no live DDMC inventory API is connected.

The runner reads inventory through the `InventoryProvider` contract in
`src/resource_dispatch/inventory_provider.py`. Its current
`WorkbookInventoryProvider` implementation validates and reads the workbook
snapshot. A future live integration can implement the same
`get_current_inventory()` method and return `resource_id`, `resource_type`,
`district`, and `available_count`; the allocation and reservation logic can
then stay unchanged. The current provider is not a network API or a live feed.

To run the dispatch and reservation unit tests, use
`python -m unittest discover -s tests -v`.

## Local allocation dashboard

Launch the desktop UI from the repository root with
`python scripts/resource_dispatch_dashboard.py`. It provides a preview of
proposed allocations, request fulfillment, inventory after reservations, and a
same-scenario comparison with the greedy reference heuristic. District,
hazard, and resource filters only affect the displayed rows; they do not rerun
or alter the allocation.

Generating a preview does not reserve resources. The **Approve and reserve
plan** button requires confirmation and writes reservations to the local CSV
ledger. This is a desktop research-prototype UI: it reads the prepared CSV
inputs and workbook inventory snapshot, and does not connect to live DDMC
inventory or dispatch systems.

## Dispatch evaluation metrics

`resource_dispatch.evaluation` provides reusable metrics for evaluating the
supplied dispatch history and optimizer allocations:

- District coverage counts an alerted district/resource pair as covered when
  it receives at least one assigned unit. Scarcity coverage is calculated only
  over pairs with a positive local scarcity score.
- Historical ETA-based coverage uses `estimated_arrival` relative to the alert
  timestamp and requires an explicit response-window duration. The ETA is not
  an actual arrival observation.
- Historical concurrent resource reuse is a proxy: it flags assignment rows
  whose recorded `assignment_time`–`status_time` intervals overlap for the same
  resource across different alerts. `status_time` is not confirmed to be a
  resource-release time, so this is not definitive duplicate-dispatch evidence.
- Optimized allocations do not have estimated arrival times; their district
  coverage must not be reported as coverage within the historical response
  window or compared as if route travel time were known.

Run `python scripts/evaluate_dispatch.py` to create a comparison report and CSV
tables under `processed_data/allocation/results/evaluation/`. The default
ETA-based windows are 30, 60, and 120 minutes; use `--windows` to select
different positive durations. These window results and the concurrent-reuse
proxy are descriptive dataset metrics, not proof that the proposal's response
time or duplicate-dispatch targets have been met.

On the current supplied records, the 30-minute ETA-based coverage is 5/5
districts (100%) and 5/5 scarcity-affected districts (100%). The optimized
plan's eventual coverage is 5/5 districts (100%) and 4/5 scarcity-affected
districts (80%), but it has no ETA and cannot be evaluated against the
first-response-window target. The recorded assignment rows have a mean first
ETA of 18.46 minutes. Four of 148 assignment rows (2.70%) are flagged by the
concurrent-reuse proxy; because `status_time` is not confirmed resource-release
time, this does not establish the proposal's duplicate-assignment target.
The supplied assignment workbook is not identified as the manual-dispatch
baseline, so a baseline improvement claim is not supported by these results.

## Same-scenario allocation benchmark

After preparing the allocation inputs, run
`python scripts/compare_allocation_methods.py` to compare the deterministic
nearest-resource greedy benchmark with the CP-SAT optimizer on the same requests,
available inventory, and candidate resource pairs. The report and CSV outputs
are written to
`processed_data/allocation/results/same_scenario_comparison/`. The greedy method
is a reproducible reference heuristic, not a reconstruction of manual DDMC
dispatch.

On the current prepared scenario, both methods cover 5/5 districts and 4/5
scarcity-affected districts, with the same fulfillment quantities by resource
type: AMB 26/50, BOAT 5/5, RLF 2,087/2,087, RT 8/61, and SHL 3,493/3,493.
Their priority/scarcity-weighted dispatch scores are also the same. The
optimizer's allocated-quantity-weighted straight-line distance is 27,570.04
km-units, compared with 28,102.32 km-units for greedy (about 1.89% lower).
This distance measure is not routed travel distance or travel time, and the
coverage results are eventual allocations, not ETA-window coverage. The
comparison does not demonstrate a live inventory feed or optimizer ETA: the
inventory source remains a workbook snapshot, and route, travel-time, and
arrival-time data are not available to the optimizer.
