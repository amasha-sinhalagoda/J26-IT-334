"""Run the resource allocation optimizer on prepared CSV inputs."""

from pathlib import Path
import sys

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch import solve_allocation
from resource_dispatch.dispatch_safety import validate_dispatch_plan


ALLOCATION_DIR = PROJECT_DIR / "processed_data" / "allocation"
RESULTS_DIR = ALLOCATION_DIR / "results"


def main():
    requests_path = ALLOCATION_DIR / "allocation_requests.csv"
    supply_path = ALLOCATION_DIR / "available_resource_supply.csv"
    candidates_path = ALLOCATION_DIR / "allocation_candidates.csv"
    inventory_path = PROJECT_DIR / "Resource_Inventory_5Districts.xlsx"
    missing = [
        path.name
        for path in [
            requests_path, supply_path, candidates_path, inventory_path,
        ]
        if not path.exists()
    ]
    if missing:
        raise FileNotFoundError(
            "Missing allocation input(s): {}. Run scripts/prepare_allocation_inputs.py first.".format(
                ", ".join(missing)
            )
        )

    result = solve_allocation(
        requests=pd.read_csv(requests_path),
        supply=pd.read_csv(supply_path),
        candidates=pd.read_csv(candidates_path),
    )
    current_inventory = pd.read_excel(
        inventory_path, sheet_name="Resource_Inventory"
    )
    result["dispatch_validation"] = validate_dispatch_plan(
        result["allocations"], current_inventory
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
        "Dispatch plan validated against current recorded workbook availability.",
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
    print("Solver statuses:")
    print(result["solver_results"].to_string(index=False))


if __name__ == "__main__":
    main()
