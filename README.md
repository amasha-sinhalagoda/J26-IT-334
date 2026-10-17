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
