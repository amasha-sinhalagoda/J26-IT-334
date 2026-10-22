"""Compare recorded dispatch metrics with the optimized allocation plan."""

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch.evaluation import (
    evaluate_district_coverage,
    evaluate_historical_dispatch,
)


PROCESSED_DIR = PROJECT_DIR / "processed_data"
ALLOCATION_DIR = PROCESSED_DIR / "allocation"
RESULTS_DIR = ALLOCATION_DIR / "results"
EVALUATION_DIR = RESULTS_DIR / "evaluation"


def _require_file(path):
    if not path.exists():
        raise FileNotFoundError(
            "{} is missing. Run preprocessing, priority scoring, allocation "
            "input preparation, and the allocation solver first.".format(path)
        )
    return path


def _district_coverage_row(label, coverage, response_window=None):
    return {
        "approach": label,
        "response_window_minutes": response_window,
        "alerted_districts": coverage["alerted_districts"],
        "districts_covered": coverage["districts_covered"],
        "district_coverage_rate": coverage["district_coverage_rate"],
        "scarce_districts": coverage["scarce_districts"],
        "scarce_districts_covered": coverage["scarce_districts_covered"],
        "scarcity_district_coverage_rate": coverage[
            "scarcity_district_coverage_rate"
        ],
    }


def run_evaluation(response_windows):
    requests = pd.read_csv(_require_file(ALLOCATION_DIR / "allocation_requests.csv"))
    assignments = pd.read_csv(
        _require_file(PROCESSED_DIR / "dispatch_assignments_clean.csv")
    )
    optimized_allocations = pd.read_csv(
        _require_file(RESULTS_DIR / "allocation_results.csv")
    )
    fulfillment = pd.read_csv(
        _require_file(RESULTS_DIR / "request_fulfillment.csv")
    )

    optimizer_coverage = evaluate_district_coverage(
        requests,
        optimized_allocations,
        district_column="district",
        resource_type_column="requested_resource_type",
        quantity_column="allocated_quantity",
    )
    optimizer_by_resource_type = fulfillment.groupby(
        "requested_resource_type", as_index=False
    ).agg(
        requested_quantity=("requested_quantity", "sum"),
        allocated_quantity=("allocated_quantity", "sum"),
        unfilled_quantity=("unfilled_quantity", "sum"),
    )
    optimizer_by_resource_type["fulfillment_rate"] = (
        optimizer_by_resource_type["allocated_quantity"]
        / optimizer_by_resource_type["requested_quantity"]
    )

    historical = [
        evaluate_historical_dispatch(
            requests,
            assignments,
            first_response_window_minutes=window,
        )
        for window in response_windows
    ]
    baseline_coverage = historical[0]["district_coverage"]
    coverage_rows = [
        _district_coverage_row(
            "recorded_assignments_within_window",
            result["district_coverage"],
            result["first_response_window_minutes"],
        )
        for result in historical
    ]
    coverage_rows.append(
        _district_coverage_row(
            "optimized_plan_eventual_allocation",
            optimizer_coverage,
        )
    )
    coverage_by_approach = pd.DataFrame(coverage_rows)

    baseline_by_resource_type = requests[
        ["alert_id", "requested_resource_type", "requested_quantity"]
    ].merge(
        assignments.groupby(
            ["alert_id", "resource_type"], as_index=False
        ).agg(assigned_quantity=("assigned_quantity", "sum")),
        left_on=["alert_id", "requested_resource_type"],
        right_on=["alert_id", "resource_type"],
        how="left",
        validate="one_to_one",
    )
    baseline_by_resource_type["assigned_quantity"] = baseline_by_resource_type[
        "assigned_quantity"
    ].fillna(0)
    baseline_by_resource_type = baseline_by_resource_type.groupby(
        "requested_resource_type", as_index=False
    ).agg(
        requested_quantity=("requested_quantity", "sum"),
        assigned_quantity=("assigned_quantity", "sum"),
    )
    baseline_by_resource_type["unfilled_quantity"] = (
        baseline_by_resource_type["requested_quantity"]
        - baseline_by_resource_type["assigned_quantity"]
    ).clip(lower=0)
    baseline_by_resource_type["assignment_rate"] = (
        baseline_by_resource_type["assigned_quantity"]
        / baseline_by_resource_type["requested_quantity"]
    )
    resource_type_comparison = baseline_by_resource_type.merge(
        optimizer_by_resource_type,
        on="requested_resource_type",
        how="outer",
        suffixes=("_recorded", "_optimized"),
        validate="one_to_one",
    ).sort_values("requested_resource_type")

    EVALUATION_DIR.mkdir(parents=True, exist_ok=True)
    coverage_by_approach.to_csv(
        EVALUATION_DIR / "district_coverage_comparison.csv",
        index=False,
        encoding="utf-8-sig",
    )
    optimizer_coverage["district_resource_results"].to_csv(
        EVALUATION_DIR / "optimized_district_resource_coverage.csv",
        index=False,
        encoding="utf-8-sig",
    )
    optimizer_by_resource_type.to_csv(
        EVALUATION_DIR / "optimized_fulfillment_by_resource_type.csv",
        index=False,
        encoding="utf-8-sig",
    )
    resource_type_comparison.to_csv(
        EVALUATION_DIR / "recorded_vs_optimized_by_resource_type.csv",
        index=False,
        encoding="utf-8-sig",
    )

    first = historical[0]
    report = [
        "Resource-aware dispatch evaluation",
        "Recorded workbook assignments are used as historical observations; they are not asserted to be a manual-dispatch baseline.",
        "The optimizer is evaluated as a proposed allocation plan, not an arrived response.",
        "estimated_arrival is an ETA, not an actual arrival time. Mean ETA differences cannot establish achieved first-response-time improvements.",
        "The optimizer has no ETA outputs, so the proposal target of at least 30% response-time reduction cannot be evaluated.",
        "Recorded concurrent resource reuse is an interval-overlap proxy using status_time, not definitive duplicate-dispatch evidence.",
        "Optimizer eventual district coverage is not first-response-window coverage.",
        "Response windows evaluated (minutes): {}".format(
            ", ".join(str(window) for window in response_windows)
        ),
        "Recorded assignment rows: {}".format(first["assignment_count"]),
        "Assignments with ETA within {} minutes: {}".format(
            response_windows[0], first["assignments_in_window"]
        ),
        "Alerts with an assignment ETA: {}".format(first["alerts_with_response"]),
        "Mean first ETA (minutes, per alert's earliest estimated arrival): {:.2f}".format(
            first["mean_first_eta_minutes"]
        ),
        "Rows flagged by concurrent-reuse proxy: {} ({:.2%})".format(
            first["concurrent_reuse_rows"], first["concurrent_reuse_rate"]
        ),
        "ETA-based district coverage by response window:",
    ]
    report.extend(
        "{} min: {}/{} districts ({:.2%}); scarce districts {}/{} ({:.2%})".format(
            result["first_response_window_minutes"],
            result["district_coverage"]["districts_covered"],
            result["district_coverage"]["alerted_districts"],
            result["district_coverage"]["district_coverage_rate"],
            result["district_coverage"]["scarce_districts_covered"],
            result["district_coverage"]["scarce_districts"],
            result["district_coverage"]["scarcity_district_coverage_rate"],
        )
        for result in historical
    )
    report.extend([
        "Optimizer eventual distinct-district coverage: {}/{} ({:.2%})".format(
            optimizer_coverage["districts_covered"],
            optimizer_coverage["alerted_districts"],
            optimizer_coverage["district_coverage_rate"],
        ),
        "Optimizer eventual scarce-district coverage: {}/{} ({:.2%})".format(
            optimizer_coverage["scarce_districts_covered"],
            optimizer_coverage["scarce_districts"],
            optimizer_coverage["scarcity_district_coverage_rate"],
        ),
        "",
        "Coverage and fulfillment tables are saved under {}".format(EVALUATION_DIR),
        "Recorded and optimized resource-type quantities should be interpreted separately: recorded assignments may represent a different operational status/time scope than the optimizer's plan.",
    ])
    (EVALUATION_DIR / "evaluation_report.txt").write_text(
        "\n".join(report), encoding="utf-8"
    )
    print("\n".join(report))
    print("\nOptimizer fulfillment by resource type:")
    print(optimizer_by_resource_type.to_string(index=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--windows",
        nargs="+",
        type=float,
        default=[30, 60, 120],
        help="response-window durations in minutes (default: 30 60 120)",
    )
    args = parser.parse_args()
    if not args.windows or any(window <= 0 for window in args.windows):
        parser.error("response windows must be positive numbers")
    run_evaluation(args.windows)


if __name__ == "__main__":
    main()
