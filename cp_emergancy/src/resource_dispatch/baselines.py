"""Deterministic greedy allocation benchmark."""

import numpy as np
import pandas as pd


ALERT_PRIORITY_WEIGHT = 0.8
LOCAL_SCARCITY_WEIGHT = 0.2

REQUEST_COLUMNS = {
    "alert_id", "requested_resource_type", "requested_quantity",
    "priority_score", "priority_rank", "local_scarcity_score",
}
SUPPLY_COLUMNS = {"resource_id", "resource_type", "available_count"}
CANDIDATE_COLUMNS = {
    "alert_id", "requested_resource_type", "requested_quantity",
    "priority_score", "local_scarcity_score", "resource_id",
    "candidate_resource_type", "available_quantity",
    "straight_line_distance_km",
}


def _require_columns(table, required, label):
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError("{} missing columns: {}".format(label, missing))


def _integer_series(table, column, label, positive=False):
    values = pd.to_numeric(table[column], errors="coerce")
    invalid = values.isna() | (values % 1 != 0)
    invalid |= values <= 0 if positive else values < 0
    if invalid.any():
        qualifier = "positive" if positive else "nonnegative"
        raise ValueError("{} must contain {} integers".format(label, qualifier))
    return values.astype("int64")


def solve_greedy_allocation(requests, supply, candidates):
    """Allocate highest dispatch-score requests to their nearest free supply.

    This is a deterministic greedy benchmark, not a replay of actual manual
    DDMC behavior. It uses the same candidate set and capacity constraints as
    the optimizer, orders requests by the optimizer's 80/20 dispatch score,
    then takes nearest resources first.
    """
    _require_columns(requests, REQUEST_COLUMNS, "Requests")
    _require_columns(supply, SUPPLY_COLUMNS, "Supply")
    _require_columns(candidates, CANDIDATE_COLUMNS, "Candidates")

    requests = requests.copy().reset_index(drop=True)
    supply = supply.copy().reset_index(drop=True)
    candidates = candidates.copy().reset_index(drop=True)
    for table in [requests, candidates]:
        table["requested_resource_type"] = (
            table["requested_resource_type"]
            .astype("string").str.strip().str.upper()
        )
        table["priority_score"] = pd.to_numeric(
            table["priority_score"], errors="coerce"
        )
        table["local_scarcity_score"] = pd.to_numeric(
            table["local_scarcity_score"], errors="coerce"
        )
    supply["resource_type"] = (
        supply["resource_type"].astype("string").str.strip().str.upper()
    )
    candidates["candidate_resource_type"] = (
        candidates["candidate_resource_type"]
        .astype("string").str.strip().str.upper()
    )
    for table, column, label in [
        (requests, "requested_quantity", "Request quantity"),
        (supply, "available_count", "Available quantity"),
        (candidates, "requested_quantity", "Candidate request quantity"),
        (candidates, "available_quantity", "Candidate availability"),
    ]:
        table[column] = _integer_series(
            table, column, label, positive=column == "requested_quantity"
        )
    candidates["straight_line_distance_km"] = pd.to_numeric(
        candidates["straight_line_distance_km"], errors="coerce"
    )
    requests["priority_rank"] = pd.to_numeric(
        requests["priority_rank"], errors="coerce"
    )

    if requests["alert_id"].isna().any() or requests.duplicated(
        ["alert_id", "requested_resource_type"]
    ).any():
        raise ValueError("Requests contain blank or duplicate alert/type keys")
    if supply["resource_id"].isna().any() or supply["resource_id"].duplicated().any():
        raise ValueError("Supply contains blank or duplicate resource IDs")
    for table in [requests, candidates]:
        if (
            table["priority_score"].isna().any()
            or (table["priority_score"] < 0).any()
            or (table["priority_score"] > 1).any()
            or table["local_scarcity_score"].isna().any()
            or (table["local_scarcity_score"] < 0).any()
            or (table["local_scarcity_score"] > 1).any()
        ):
            raise ValueError("Priority and scarcity scores must be between 0 and 1")
    if (
        candidates["straight_line_distance_km"].isna().any()
        or not np.isfinite(candidates["straight_line_distance_km"]).all()
        or (candidates["straight_line_distance_km"] < 0).any()
    ):
        raise ValueError("Candidate distances must be finite and nonnegative")
    if (
        requests["priority_rank"].isna().any()
        or not np.isfinite(requests["priority_rank"]).all()
        or (requests["priority_rank"] < 1).any()
        or (requests["priority_rank"] % 1 != 0).any()
    ):
        raise ValueError("Priority ranks must be positive integers")

    request_keys = set(zip(
        requests["alert_id"], requests["requested_resource_type"]
    ))
    candidate_keys = set(zip(
        candidates["alert_id"], candidates["requested_resource_type"]
    ))
    if not candidate_keys.issubset(request_keys):
        raise ValueError("Candidates contain keys absent from requests")
    if candidates.duplicated(
        ["alert_id", "requested_resource_type", "resource_id"]
    ).any():
        raise ValueError("Candidates contain duplicate alert/resource pairs")

    supply_by_id = supply.set_index("resource_id")
    if not candidates["resource_id"].isin(supply_by_id.index).all():
        raise ValueError("A candidate refers to a resource absent from supply")
    if (
        candidates["candidate_resource_type"]
        != candidates["resource_id"].map(supply_by_id["resource_type"])
    ).any():
        raise ValueError("Candidate resource type disagrees with supply")
    if (
        candidates["available_quantity"]
        != candidates["resource_id"].map(supply_by_id["available_count"])
    ).any():
        raise ValueError("Candidate availability disagrees with supply")
    if (candidates["available_quantity"] <= 0).any():
        raise ValueError("Candidates must reference available resources")

    request_values = requests.set_index(
        ["alert_id", "requested_resource_type"]
    )[["requested_quantity", "priority_score", "local_scarcity_score"]]
    checked_candidates = candidates.merge(
        request_values.reset_index(),
        on=["alert_id", "requested_resource_type"],
        suffixes=("_candidate", "_request"),
        validate="many_to_one",
    )
    for column in [
        "requested_quantity", "priority_score", "local_scarcity_score",
    ]:
        if (
            checked_candidates["{}_candidate".format(column)]
            - checked_candidates["{}_request".format(column)]
        ).abs().gt(1e-9).any():
            raise ValueError(
                "Candidate {} disagrees with request input".format(column)
            )

    requests["dispatch_score"] = (
        ALERT_PRIORITY_WEIGHT * requests["priority_score"]
        + LOCAL_SCARCITY_WEIGHT * requests["local_scarcity_score"]
    )
    request_order = requests.sort_values(
        ["dispatch_score", "priority_rank", "alert_id"],
        ascending=[False, True, True],
        kind="mergesort",
    )
    remaining_by_resource = supply.set_index("resource_id")[
        "available_count"
    ].to_dict()
    rows = []
    for _, request in request_order.iterrows():
        key = (request["alert_id"], request["requested_resource_type"])
        remaining_demand = int(request["requested_quantity"])
        options = candidates.loc[
            (candidates["alert_id"] == key[0])
            & (candidates["requested_resource_type"] == key[1])
        ].sort_values(
            ["straight_line_distance_km", "resource_id"],
            kind="mergesort",
        )
        for _, candidate in options.iterrows():
            available = remaining_by_resource[candidate["resource_id"]]
            allocated = min(remaining_demand, int(available))
            if allocated <= 0:
                continue
            remaining_by_resource[candidate["resource_id"]] -= allocated
            remaining_demand -= allocated
            row = candidate.to_dict()
            row["allocated_quantity"] = allocated
            rows.append(row)
            if remaining_demand == 0:
                break

    allocation_columns = [
        "alert_id", "requested_resource_type", "district", "GN_division",
        "priority_score", "priority_rank", "local_scarcity_score",
        "requested_quantity", "resource_id", "resource_district",
        "available_quantity", "allocated_quantity",
        "straight_line_distance_km", "is_same_district",
    ]
    allocations = pd.DataFrame(rows)
    if allocations.empty:
        allocations = pd.DataFrame(columns=allocation_columns)
    else:
        allocations = allocations[
            [column for column in allocation_columns if column in allocations]
        ]

    if allocations.empty:
        allocated_by_request = pd.DataFrame(columns=[
            "alert_id", "requested_resource_type", "allocated_quantity",
        ])
    else:
        allocated_by_request = allocations.groupby(
            ["alert_id", "requested_resource_type"], as_index=False
        )["allocated_quantity"].sum()
    request_results = requests.drop(columns="dispatch_score").merge(
        allocated_by_request,
        on=["alert_id", "requested_resource_type"],
        how="left",
        validate="one_to_one",
    )
    request_results["allocated_quantity"] = request_results[
        "allocated_quantity"
    ].fillna(0).astype("int64")
    request_results["unfilled_quantity"] = (
        request_results["requested_quantity"]
        - request_results["allocated_quantity"]
    )
    request_results["fulfillment_rate"] = (
        request_results["allocated_quantity"]
        / request_results["requested_quantity"]
    )

    if allocations.empty:
        allocated_by_resource = pd.DataFrame(columns=[
            "resource_id", "allocated_quantity",
        ])
    else:
        allocated_by_resource = allocations.groupby(
            "resource_id", as_index=False
        )["allocated_quantity"].sum()
    resource_results = supply.merge(
        allocated_by_resource,
        on="resource_id",
        how="left",
        validate="one_to_one",
    )
    resource_results["allocated_quantity"] = resource_results[
        "allocated_quantity"
    ].fillna(0).astype("int64")
    resource_results["remaining_quantity"] = (
        resource_results["available_count"]
        - resource_results["allocated_quantity"]
    )
    return {
        "allocations": allocations.reset_index(drop=True),
        "request_results": request_results.reset_index(drop=True),
        "resource_results": resource_results.reset_index(drop=True),
    }
