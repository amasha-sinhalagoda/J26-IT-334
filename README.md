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
