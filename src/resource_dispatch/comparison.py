"""Same-scenario comparison of the CP-SAT and greedy dispatch methods."""

import pandas as pd

from .allocator import (
    ALERT_PRIORITY_WEIGHT,
    LOCAL_SCARCITY_WEIGHT,
    solve_allocation,
)
from .baselines import solve_greedy_allocation
from .evaluation import evaluate_district_coverage


def _method_metrics(name, requests, supply, result):
    coverage = evaluate_district_coverage(
        requests,
        result["allocations"],
        district_column="district",
        resource_type_column="requested_resource_type",
        quantity_column="allocated_quantity",
    )
    request_results = result["request_results"]
    resource_results = result["resource_results"]
    allocations = result["allocations"]
    requested_districts = sorted(requests["district"].dropna().unique())
    district_resource = coverage["district_resource_results"]
    covered_districts = set(
        district_resource.loc[
            district_resource["covered"], "district"
        ].str.casefold()
    )
    scarce_districts = set(
        district_resource.loc[
            district_resource["scarcity_area"], "district"
        ].str.casefold()
    )
    covered_scarce_districts = set(
        district_resource.loc[
            district_resource["scarcity_area"] & district_resource["covered"],
            "district",
        ].str.casefold()
    )

    method_summary = {
        "method": name,
        "alerted_districts": len(requested_districts),
        "districts_covered": len(covered_districts),
        "district_coverage_rate": (
            len(covered_districts) / len(requested_districts)
            if requested_districts
            else 0.0
        ),
        "scarce_districts": len(scarce_districts),
        "scarce_districts_covered": len(covered_scarce_districts),
        "scarcity_district_coverage_rate": (
            len(covered_scarce_districts) / len(scarce_districts)
            if scarce_districts
            else 0.0
        ),
        "requested_resource_type_units": (
            "Not aggregated across types: unit scales differ by type."
        ),
        "dispatch_score_weighted_units": (
            (
                ALERT_PRIORITY_WEIGHT * allocations["priority_score"]
                + LOCAL_SCARCITY_WEIGHT * allocations["local_scarcity_score"]
            )
            * allocations["allocated_quantity"]
        ).sum(),
        "straight_line_quantity_distance_km": (
            allocations["straight_line_distance_km"]
            * allocations["allocated_quantity"]
        ).sum(),
    }

    resource_type_metrics = request_results.groupby(
        "requested_resource_type", as_index=False
    ).agg(
        requested_quantity=("requested_quantity", "sum"),
        allocated_quantity=("allocated_quantity", "sum"),
        unfilled_quantity=("unfilled_quantity", "sum"),
    )
    supply_by_type = supply.groupby(
        "resource_type", as_index=False
    ).agg(available_quantity=("available_count", "sum"))
    used_resources = resource_results.loc[
        resource_results["allocated_quantity"] > 0
    ].groupby("resource_type").size()
    resource_type_metrics = resource_type_metrics.merge(
        supply_by_type,
        left_on="requested_resource_type",
        right_on="resource_type",
        how="left",
        validate="one_to_one",
    ).drop(columns="resource_type")
    resource_type_metrics["resources_used"] = (
        resource_type_metrics["requested_resource_type"]
        .map(used_resources)
        .fillna(0)
        .astype("int64")
    )
    resource_count = resource_results.groupby("resource_type").size()
    resource_type_metrics["resources_available"] = (
        resource_type_metrics["requested_resource_type"]
        .map(resource_count)
        .fillna(0)
        .astype("int64")
    )
    resource_type_metrics["fulfillment_rate"] = (
        resource_type_metrics["allocated_quantity"]
        / resource_type_metrics["requested_quantity"]
    )
    resource_type_metrics["quantity_utilization_rate"] = (
        resource_type_metrics["allocated_quantity"]
        / resource_type_metrics["available_quantity"]
    ).where(resource_type_metrics["available_quantity"] > 0, 0.0)
    resource_type_metrics["resource_record_utilization_rate"] = (
        resource_type_metrics["resources_used"]
        / resource_type_metrics["resources_available"]
    ).where(resource_type_metrics["resources_available"] > 0, 0.0)
    resource_type_metrics.insert(0, "method", name)

    district_metrics = district_resource.copy()
    district_metrics.insert(0, "method", name)
    district_metrics["requested_resource_type"] = (
        district_metrics["requested_resource_type"].astype("string").str.upper()
    )
    return method_summary, resource_type_metrics, district_metrics


def _request_comparison(requests, greedy, optimized):
    def prepare(result, name):
        return result["request_results"][
            [
                "alert_id", "requested_resource_type", "allocated_quantity",
                "unfilled_quantity",
            ]
        ].rename(columns={
            "allocated_quantity": "{}_allocated_quantity".format(name),
            "unfilled_quantity": "{}_unfilled_quantity".format(name),
        })

    comparison = requests[
        [
            "alert_id", "district", "requested_resource_type",
            "requested_quantity", "priority_score", "local_scarcity_score",
        ]
    ].merge(
        prepare(greedy, "greedy"),
        on=["alert_id", "requested_resource_type"],
        how="left",
        validate="one_to_one",
    ).merge(
        prepare(optimized, "optimizer"),
        on=["alert_id", "requested_resource_type"],
        how="left",
        validate="one_to_one",
    )
    if comparison[
        [
            "greedy_allocated_quantity", "greedy_unfilled_quantity",
            "optimizer_allocated_quantity", "optimizer_unfilled_quantity",
        ]
    ].isna().any().any():
        raise AssertionError("A comparison method omitted one or more requests")
    return comparison


def compare_allocation_methods(requests, supply, candidates):
    """Run both allocation approaches on the exact same scenario inputs."""
    greedy = solve_greedy_allocation(requests, supply, candidates)
    optimized = solve_allocation(requests, supply, candidates)
    methods = [
        ("greedy_nearest", greedy),
        ("cp_sat_optimizer", optimized),
    ]

    method_rows = []
    type_tables = []
    district_tables = []
    for name, result in methods:
        method_row, type_metrics, district_metrics = _method_metrics(
            name, requests, supply, result
        )
        method_rows.append(method_row)
        type_tables.append(type_metrics)
        district_tables.append(district_metrics)

    return {
        "method_summary": pd.DataFrame(method_rows),
        "resource_type_metrics": pd.concat(
            type_tables, ignore_index=True
        ),
        "district_resource_metrics": pd.concat(
            district_tables, ignore_index=True
        ),
        "request_comparison": _request_comparison(
            requests, greedy, optimized
        ),
        "greedy": greedy,
        "optimizer": optimized,
    }
