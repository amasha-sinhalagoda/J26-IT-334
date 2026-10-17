# J26-IT-334
Research project repository for J26-IT-334, containing research documentation, datasets, source code, system development resources, and project-related materials.

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

To run the dispatch and reservation unit tests, use
`python -m unittest discover -s tests -v`.

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
