"""Compare greedy and CP-SAT allocation on the same prepared scenario."""

from pathlib import Path
import sys

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch.comparison import compare_allocation_methods


ALLOCATION_DIR = PROJECT_DIR / "processed_data" / "allocation"
RESULTS_DIR = ALLOCATION_DIR / "results" / "same_scenario_comparison"


def main():
    inputs = {
        "requests": ALLOCATION_DIR / "allocation_requests.csv",
        "supply": ALLOCATION_DIR / "available_resource_supply.csv",
        "candidates": ALLOCATION_DIR / "allocation_candidates.csv",
    }
    missing = [str(path) for path in inputs.values() if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Missing prepared scenario input(s): {}. Run scripts/prepare_allocation_inputs.py first.".format(
                ", ".join(missing)
            )
        )

    result = compare_allocation_methods(
        requests=pd.read_csv(inputs["requests"]),
        supply=pd.read_csv(inputs["supply"]),
        candidates=pd.read_csv(inputs["candidates"]),
    )
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_tables = {
        "method_summary.csv": result["method_summary"],
        "resource_type_metrics.csv": result["resource_type_metrics"],
        "district_resource_metrics.csv": result["district_resource_metrics"],
        "request_comparison.csv": result["request_comparison"],
        "greedy_allocations.csv": result["greedy"]["allocations"],
        "optimizer_allocations.csv": result["optimizer"]["allocations"],
    }
    for filename, table in output_tables.items():
        table.to_csv(
            RESULTS_DIR / filename,
            index=False,
            encoding="utf-8-sig",
        )

    report = [
        "Same-scenario allocation method comparison",
        "Methods: deterministic greedy nearest-resource benchmark and CP-SAT optimizer.",
        "Both methods receive identical prepared requests, inventory availability, and candidate resource pairs.",
        "This greedy benchmark is not a reconstruction of actual manual DDMC operations.",
        "District coverage is eventual allocation coverage, not coverage within a response-time window.",
        "Resource quantity utilization is reported by resource type because units differ across types.",
        "",
        "District coverage:",
    ]
    report.extend(
        "{}: districts {}/{}, scarce districts {}/{}, weighted dispatch score {:.2f}, straight-line quantity-distance {:.2f} km-units".format(
            row.method,
            row.districts_covered,
            row.alerted_districts,
            row.scarce_districts_covered,
            row.scarce_districts,
            row.dispatch_score_weighted_units,
            row.straight_line_quantity_distance_km,
        )
        for row in result["method_summary"].itertuples(index=False)
    )
    report.extend(["", "Fulfillment and utilization by resource type:"])
    report.extend(
        "{} {}: allocated {}/{}, unfilled {}, fulfillment {:.2%}, quantity utilization {:.2%}, resource records used {}/{}".format(
            row.method,
            row.requested_resource_type,
            int(row.allocated_quantity),
            int(row.requested_quantity),
            int(row.unfilled_quantity),
            row.fulfillment_rate,
            row.quantity_utilization_rate,
            int(row.resources_used),
            int(row.resources_available),
        )
        for row in result["resource_type_metrics"].itertuples(index=False)
    )
    report.extend([
        "",
        "The optimizer maximizes its priority/scarcity-weighted objective and need not maximize raw filled units or geographic coverage.",
        "Weighted dispatch score uses the same 80/20 priority/scarcity blend as the allocator. Straight-line quantity-distance is an un-routed proxy (allocated units multiplied by straight-line distance), not travel time.",
        "Metrics and per-request allocation differences are saved under {}".format(RESULTS_DIR),
    ])
    (RESULTS_DIR / "comparison_report.txt").write_text(
        "\n".join(report), encoding="utf-8"
    )
    print("\n".join(report))


if __name__ == "__main__":
    main()
