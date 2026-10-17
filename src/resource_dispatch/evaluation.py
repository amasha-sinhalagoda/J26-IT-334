"""Comparative allocation metrics for resource-aware dispatch evaluation."""

import numpy as np
import pandas as pd


def _require_columns(table, required, label):
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError("{} missing columns: {}".format(label, missing))


def _normalize(series):
    return series.astype("string").str.strip().str.casefold()


def _validate_quantities(series, label):
    values = pd.to_numeric(series, errors="coerce")
    if (
        values.isna().any()
        or not np.isfinite(values).all()
        or (values < 0).any()
    ):
        raise ValueError("{} must contain finite nonnegative values".format(label))
    return values


def evaluate_district_coverage(requests, service_records, district_column,
                               resource_type_column, quantity_column):
    """Measure all-demand and local-shortage district coverage from allocations.

    A district/resource pair is covered when it receives at least one unit.
    Scarcity coverage counts only pairs with a positive local scarcity score.
    These coverage measures do not imply that service arrived within a time
    window; use historical arrival records for timed coverage.
    """
    _require_columns(
        requests,
        {
            "district", "requested_resource_type", "requested_quantity",
            "local_scarcity_score",
        },
        "Requests",
    )
    _require_columns(
        service_records,
        {district_column, resource_type_column, quantity_column},
        "Service records",
    )
    demand = requests[
        [
            "district", "requested_resource_type", "requested_quantity",
            "local_scarcity_score",
        ]
    ].copy()
    served = service_records[
        [district_column, resource_type_column, quantity_column]
    ].copy()
    demand["requested_quantity"] = _validate_quantities(
        demand["requested_quantity"], "Requested quantity"
    )
    demand["local_scarcity_score"] = pd.to_numeric(
        demand["local_scarcity_score"], errors="coerce"
    )
    served[quantity_column] = _validate_quantities(
        served[quantity_column], "Served quantity"
    )
    if (
        demand["local_scarcity_score"].isna().any()
        or not np.isfinite(demand["local_scarcity_score"]).all()
        or (demand["local_scarcity_score"] < 0).any()
        or (demand["local_scarcity_score"] > 1).any()
    ):
        raise ValueError("Local scarcity scores must be between 0 and 1")

    demand["_district_key"] = _normalize(demand["district"])
    demand["_resource_type_key"] = _normalize(
        demand["requested_resource_type"]
    )
    served["_district_key"] = _normalize(served[district_column])
    served["_resource_type_key"] = _normalize(served[resource_type_column])
    if (
        demand[["_district_key", "_resource_type_key"]].isna().any().any()
        or demand[["_district_key", "_resource_type_key"]].eq("").any().any()
        or served[["_district_key", "_resource_type_key"]].isna().any().any()
        or served[["_district_key", "_resource_type_key"]].eq("").any().any()
    ):
        raise ValueError("District and resource type values must be present")

    demand_by_area = demand.groupby(
        ["_district_key", "_resource_type_key"], as_index=False
    ).agg(
        district=("district", "first"),
        requested_resource_type=("requested_resource_type", "first"),
        local_scarcity_score=("local_scarcity_score", "max"),
    )
    served_by_area = served.groupby(
        ["_district_key", "_resource_type_key"], as_index=False
    )[quantity_column].sum()
    area_results = demand_by_area.merge(
        served_by_area,
        on=["_district_key", "_resource_type_key"],
        how="left",
        validate="one_to_one",
    )
    area_results[quantity_column] = area_results[quantity_column].fillna(0)
    area_results["covered"] = area_results[quantity_column] > 0
    area_results["scarcity_area"] = area_results["local_scarcity_score"] > 0

    all_districts = set(area_results["_district_key"])
    covered_districts = set(
        area_results.loc[area_results["covered"], "_district_key"]
    )
    scarce_districts = set(
        area_results.loc[area_results["scarcity_area"], "_district_key"]
    )
    covered_scarce_districts = set(
        area_results.loc[
            area_results["scarcity_area"] & area_results["covered"],
            "_district_key",
        ]
    )
    return {
        "alerted_districts": len(all_districts),
        "districts_covered": len(covered_districts),
        "district_coverage_rate": (
            len(covered_districts) / len(all_districts) if all_districts else 0.0
        ),
        "scarce_districts": len(scarce_districts),
        "scarce_districts_covered": len(covered_scarce_districts),
        "scarcity_district_coverage_rate": (
            len(covered_scarce_districts) / len(scarce_districts)
            if scarce_districts
            else 0.0
        ),
        "district_resource_results": area_results.drop(
            columns=["_district_key", "_resource_type_key"]
        ).reset_index(drop=True),
    }


def evaluate_historical_dispatch(requests, assignments,
                                 first_response_window_minutes):
    """Measure ETA-based response-window coverage and concurrent reuse proxy.

    Response estimates use estimated_arrival minus alert timestamp; ETAs are
    not actual arrival observations. Concurrent reuse is a proxy based on
    overlaps between assignment_time and status_time for the same resource
    serving different alerts. status_time is not a confirmed resource-release
    time, so this is not definitive proof of duplicate dispatch.
    """
    if (
        not isinstance(first_response_window_minutes, (int, float))
        or not np.isfinite(first_response_window_minutes)
        or first_response_window_minutes <= 0
    ):
        raise ValueError("First-response window must be a positive number of minutes")
    _require_columns(
        requests,
        {
            "alert_id", "district", "requested_resource_type", "timestamp",
            "local_scarcity_score",
        },
        "Requests",
    )
    _require_columns(
        assignments,
        {
            "alert_id", "resource_id", "resource_type", "assigned_quantity",
            "assignment_time", "estimated_arrival", "status_time",
        },
        "Assignments",
    )

    alert_requests = requests[
        [
            "alert_id", "district", "requested_resource_type", "timestamp",
            "requested_quantity", "local_scarcity_score",
        ]
    ].copy()
    history = assignments[
        [
            "alert_id", "resource_id", "resource_type", "assigned_quantity",
            "assignment_time", "estimated_arrival", "status_time",
        ]
    ].copy()
    alert_requests["requested_resource_type"] = _normalize(
        alert_requests["requested_resource_type"]
    )
    history["resource_type"] = _normalize(history["resource_type"])
    history["assigned_quantity"] = _validate_quantities(
        history["assigned_quantity"], "Assigned quantity"
    )
    if (history["assigned_quantity"] <= 0).any():
        raise ValueError("Assigned quantities must be positive")
    for column in ["timestamp"]:
        alert_requests[column] = pd.to_datetime(
            alert_requests[column], errors="coerce"
        )
    for column in ["assignment_time", "estimated_arrival", "status_time"]:
        history[column] = pd.to_datetime(history[column], errors="coerce")
    if alert_requests["timestamp"].isna().any():
        raise ValueError("Requests contain invalid alert timestamps")
    if history[
        ["assignment_time", "estimated_arrival", "status_time"]
    ].isna().any().any():
        raise ValueError("Assignments contain invalid timing values")
    if history["resource_id"].isna().any() or history["alert_id"].isna().any():
        raise ValueError("Assignments contain blank resource or alert IDs")
    if (history["status_time"] < history["assignment_time"]).any():
        raise ValueError("Assignment status time precedes assignment time")

    if alert_requests.duplicated(
        ["alert_id", "requested_resource_type"]
    ).any():
        raise ValueError("Requests contain duplicate alert/resource-type pairs")
    history = history.merge(
        alert_requests,
        left_on=["alert_id", "resource_type"],
        right_on=["alert_id", "requested_resource_type"],
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    if (history["_merge"] != "both").any():
        raise ValueError("Assignments refer to requests absent from alert inputs")
    history = history.drop(columns=["_merge", "requested_resource_type"])
    deadline = history["timestamp"] + pd.to_timedelta(
        first_response_window_minutes, unit="m"
    )
    arrived_in_window = history["estimated_arrival"] <= deadline
    response_times = (
        history.assign(
            first_response_minutes=(
                history["estimated_arrival"] - history["timestamp"]
            ).dt.total_seconds() / 60.0
        )
        .groupby("alert_id")["first_response_minutes"]
        .min()
    )
    if (response_times < 0).any():
        raise ValueError("An estimated arrival precedes its alert timestamp")
    timed_service = history.loc[
        arrived_in_window,
        [
            "alert_id", "district", "resource_type", "assigned_quantity",
            "requested_quantity", "local_scarcity_score",
        ],
    ].rename(
        columns={
            "resource_type": "requested_resource_type",
            "assigned_quantity": "served_quantity",
        }
    )
    coverage_requests = alert_requests.drop_duplicates(
        ["alert_id", "requested_resource_type"]
    )
    coverage = evaluate_district_coverage(
        coverage_requests,
        timed_service,
        district_column="district",
        resource_type_column="requested_resource_type",
        quantity_column="served_quantity",
    )

    duplicate_rows = set()
    for _, resource_history in history.groupby("resource_id"):
        rows = list(resource_history.sort_values("assignment_time").iterrows())
        for index, current in rows:
            for other_index, other in rows:
                if index >= other_index:
                    continue
                overlaps = (
                    current["assignment_time"] < other["status_time"]
                    and other["assignment_time"] < current["status_time"]
                )
                if overlaps and current["alert_id"] != other["alert_id"]:
                    duplicate_rows.add(index)
                    duplicate_rows.add(other_index)

    assignment_count = len(history)
    return {
        "first_response_window_minutes": float(first_response_window_minutes),
        "assignments_in_window": int(arrived_in_window.sum()),
        "assignment_count": assignment_count,
        "alerts_with_response": int(response_times.count()),
        "mean_first_eta_minutes": (
            float(response_times.mean()) if not response_times.empty else None
        ),
        "concurrent_reuse_rows": len(duplicate_rows),
        "concurrent_reuse_rate": (
            len(duplicate_rows) / assignment_count if assignment_count else 0.0
        ),
        "concurrent_reuse_definition": (
            "Share of assignment rows participating in overlapping recorded "
            "assignment_time-status_time intervals for the same resource and "
            "different alerts; status_time is only a proxy for resource release."
        ),
        "district_coverage": coverage,
    }
