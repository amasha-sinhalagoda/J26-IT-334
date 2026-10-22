"""Run the resource allocation optimizer on prepared CSV inputs."""

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch import solve_allocation
from resource_dispatch.dispatch_safety import (
    inventory_after_reservations,
    load_reservations,
    reserve_dispatch_plan,
    validate_dispatch_plan,
)
from resource_dispatch.inventory_provider import WorkbookInventoryProvider
from resource_dispatch.scarcity import calculate_local_scarcity


ALLOCATION_DIR = PROJECT_DIR / "processed_data" / "allocation"
RESULTS_DIR = ALLOCATION_DIR / "results"
RESERVATIONS_PATH = ALLOCATION_DIR / "reservations.csv"


def _normalized_key(series):
    return series.astype("string").str.strip().str.casefold()


def _prepare_pending_inputs(requests, candidates, inventory, reservations):
    """Remove reserved demand/supply and refresh local scarcity for this run."""
    effective_inventory = inventory_after_reservations(inventory, reservations)

    if not reservations.empty:
        reserved_demand = reservations.groupby(
            ["alert_id", "requested_resource_type"], as_index=False
        )["reserved_quantity"].sum()
        requests = requests.merge(
            reserved_demand,
            on=["alert_id", "requested_resource_type"],
            how="left",
            validate="one_to_one",
        )
        requests["reserved_quantity"] = requests["reserved_quantity"].fillna(0)
        requests["requested_quantity"] = (
            requests["requested_quantity"] - requests["reserved_quantity"]
        )
        if (requests["requested_quantity"] < 0).any():
            raise ValueError(
                "Existing reservations exceed one or more request quantities"
            )
        requests = requests.loc[requests["requested_quantity"] > 0].copy()

    scarcity_inventory = effective_inventory[
        ["resource_id", "resource_type", "district", "available_count"]
    ]
    scarcity = calculate_local_scarcity(requests, scarcity_inventory)
    requests["_district_key"] = _normalized_key(requests["district"])
    requests["_resource_type_key"] = _normalized_key(
        requests["requested_resource_type"]
    )
    requests = requests.drop(
        columns=[
            "local_demand_quantity", "local_available_quantity",
            "local_shortage_quantity", "local_scarcity_score",
        ],
        errors="ignore",
    )
    requests = requests.merge(
        scarcity[
            [
                "_district_key", "_resource_type_key", "local_demand_quantity",
                "local_available_quantity", "local_shortage_quantity",
                "local_scarcity_score",
            ]
        ],
        on=["_district_key", "_resource_type_key"],
        how="left",
        validate="many_to_one",
    ).drop(columns=["_district_key", "_resource_type_key"])

    available_supply = effective_inventory.loc[
        effective_inventory["available_count"] > 0
    ].copy()
    supply_by_id = available_supply.set_index("resource_id")["available_count"]
    candidates = candidates.loc[
        candidates["alert_id"].isin(requests["alert_id"])
    ].copy()
    candidates = candidates.loc[
        candidates["resource_id"].isin(supply_by_id.index)
    ].copy()
    candidates["available_quantity"] = candidates["resource_id"].map(supply_by_id)
    candidate_fields = [
        "alert_id", "requested_resource_type", "requested_quantity",
        "priority_score", "priority_rank", "local_scarcity_score",
    ]
    candidates = candidates.drop(
        columns=[
            column for column in candidate_fields[2:]
            if column in candidates.columns
        ]
    )
    candidates = candidates.merge(
        requests[candidate_fields],
        on=["alert_id", "requested_resource_type"],
        how="inner",
        validate="many_to_one",
    )
    return (
        requests.drop(columns=["reserved_quantity"], errors="ignore"),
        available_supply,
        candidates,
    )


def main():
    parser = argparse.ArgumentParser(
        description="Prepare an allocation plan; use --approve to reserve its quantities."
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="persist this plan as reserved inventory; without this flag, run in preview mode",
    )
    args = parser.parse_args()

    requests_path = ALLOCATION_DIR / "allocation_requests.csv"
    candidates_path = ALLOCATION_DIR / "allocation_candidates.csv"
    inventory_path = PROJECT_DIR / "Resource_Inventory_5Districts.xlsx"
    missing = [
        path.name
        for path in [
            requests_path, candidates_path, inventory_path,
        ]
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Missing allocation input(s): {}. Run scripts/prepare_allocation_inputs.py first.".format(
                ", ".join(missing)
            )
        )

    requests = pd.read_csv(requests_path)
    candidates = pd.read_csv(candidates_path)
    inventory_provider = WorkbookInventoryProvider(inventory_path)
    current_inventory = inventory_provider.get_current_inventory()
    reservations = load_reservations(RESERVATIONS_PATH)
    pending_requests, available_supply, pending_candidates = _prepare_pending_inputs(
        requests, candidates, current_inventory, reservations
    )
    reserved_before_run = (
        int(reservations["reserved_quantity"].sum())
        if not reservations.empty
        else 0
    )
    solver_supply_columns = [
        "resource_id", "resource_type", "available_count",
    ]
    result = solve_allocation(
        requests=pending_requests,
        supply=available_supply[solver_supply_columns],
        candidates=pending_candidates,
    )
    result["dispatch_validation"] = validate_dispatch_plan(
        result["allocations"],
        inventory_after_reservations(current_inventory, reservations),
    )
    if args.approve:
        reservations = reserve_dispatch_plan(
            result["allocations"],
            requests,
            current_inventory,
            RESERVATIONS_PATH,
        )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    result["allocations"].to_csv(
        RESULTS_DIR / "allocation_results.csv", index=False, encoding="utf-8-sig"
    )
    result["request_results"].to_csv(
        RESULTS_DIR / "request_fulfillment.csv", index=False, encoding="utf-8-sig"
    )
    result["resource_results"].to_csv(
        RESULTS_DIR / "resource_utilization.csv", index=False, encoding="utf-8-sig"
    )
    result["solver_results"].to_csv(
        RESULTS_DIR / "solver_summary.csv", index=False, encoding="utf-8-sig"
    )

    summary = result["request_results"]
    report = [
        "Resource allocation solver run",
        "Method: OR-Tools CP-SAT, solved separately for each resource type.",
        "Dispatch score = 0.80*alert priority score + 0.20*local scarcity score.",
        "Local scarcity is the district/resource demand fraction not covered by local supply.",
        "Stage 1 maximizes dispatch-score-weighted allocated units.",
        "Stage 2 minimizes straight-line distance while preserving the stage-1 objective.",
        "Mode: {}".format("approved and reserved" if args.approve else "preview"),
        "Inventory provider: WorkbookInventoryProvider (recorded workbook snapshot).",
        "Existing reserved units subtracted before optimization: {}".format(
            reserved_before_run
        ),
        "Inventory reservation ledger: {}".format(RESERVATIONS_PATH),
        "This is a research prototype using the supplied project datasets; coordinates are approximate and distances are not route distances.",
        "Request rows: {}".format(len(summary)),
        "Fully satisfied requests: {}".format(
            int((summary["unfilled_quantity"] == 0).sum())
        ),
        "Partially/unfilled requests: {}".format(
            int((summary["unfilled_quantity"] > 0).sum())
        ),
        "Requested quantity: {}".format(int(summary["requested_quantity"].sum())),
        "Allocated quantity: {}".format(int(summary["allocated_quantity"].sum())),
        "Unfilled quantity: {}".format(int(summary["unfilled_quantity"].sum())),
        "",
        "Solver status by resource type:",
    ]
    report.extend(
        "{}: combined priority/scarcity={}, alert priority={}, scarcity={}, priority_status={}, distance_status={}".format(
            row.resource_type,
            row.combined_priority_scarcity_units,
            row.alert_priority_weighted_units,
            row.scarcity_weighted_units,
            row.priority_stage_status,
            row.distance_stage_status,
        )
        for row in result["solver_results"].itertuples(index=False)
    )
    (RESULTS_DIR / "allocation_run_report.txt").write_text(
        "\n".join(report), encoding="utf-8"
    )

    print("Allocation optimization completed.")
    print("Request rows:", len(summary))
    print("Allocated units:", int(summary["allocated_quantity"].sum()))
    print("Unfilled units:", int(summary["unfilled_quantity"].sum()))
    print("Results folder:", RESULTS_DIR)
    if args.approve:
        print("Approved plan reserved in:", RESERVATIONS_PATH)
    else:
        print("Preview only; no inventory was reserved. Use --approve to reserve this plan.")
    print("Solver statuses:")
    print(result["solver_results"].to_string(index=False))


if __name__ == "__main__":
    main()
