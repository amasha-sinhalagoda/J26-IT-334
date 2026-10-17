"""Priority-weighted resource allocation using OR-Tools CP-SAT."""

from collections import defaultdict

import pandas as pd
from ortools.sat.python import cp_model


REQUEST_COLUMNS = {
    "alert_id", "requested_resource_type", "requested_quantity",
    "priority_score", "priority_rank", "local_scarcity_score",
}
SUPPLY_COLUMNS = {"resource_id", "resource_type", "available_count"}
CANDIDATE_COLUMNS = {
    "alert_id", "requested_resource_type", "requested_quantity",
    "priority_score", "resource_id", "candidate_resource_type",
    "available_quantity", "straight_line_distance_km", "local_scarcity_score",
}
PRIORITY_SCALE = 1_000_000
DISTANCE_SCALE = 1_000
ALERT_PRIORITY_WEIGHT = 0.8
LOCAL_SCARCITY_WEIGHT = 0.2


def _require_columns(table, required, label):
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError("{} missing columns: {}".format(label, missing))


def _integer_series(table, column, label):
    values = pd.to_numeric(table[column], errors="coerce")
    if values.isna().any() or (values < 0).any() or (values % 1 != 0).any():
        raise ValueError(
            "{} must contain nonnegative integer values".format(label)
        )
    return values.astype(int)


def solve_allocation(requests, supply, candidates, max_time_seconds=20):
    """Allocate integer quantities while respecting each request and resource.

    The solver runs one CP-SAT model per resource type because units differ
    between resource types (for example, vehicles, people, and relief kits).
    The dispatch score is 80% alert priority and 20% local scarcity, where
    scarcity is the local demand fraction not covered by local supply. It first
    maximizes score-weighted allocated quantities, then minimizes straight-line
    distance among solutions with the same score objective. Distance is only a
    proxy, not a route or travel-time estimate.
    """
    _require_columns(requests, REQUEST_COLUMNS, "Requests")
    _require_columns(supply, SUPPLY_COLUMNS, "Supply")
    _require_columns(candidates, CANDIDATE_COLUMNS, "Candidates")

    requests = requests.copy().reset_index(drop=True)
    supply = supply.copy().reset_index(drop=True)
    candidates = candidates.copy().reset_index(drop=True)

    requests["requested_resource_type"] = (
        requests["requested_resource_type"].astype("string").str.strip().str.upper()
    )
    supply["resource_type"] = (
        supply["resource_type"].astype("string").str.strip().str.upper()
    )
    candidates["requested_resource_type"] = (
        candidates["requested_resource_type"].astype("string").str.strip().str.upper()
    )
    candidates["candidate_resource_type"] = (
        candidates["candidate_resource_type"].astype("string").str.strip().str.upper()
    )

    requests["requested_quantity"] = _integer_series(
        requests, "requested_quantity", "Requested quantity"
    )
    supply["available_count"] = _integer_series(
        supply, "available_count", "Available supply"
    )
    candidates["requested_quantity"] = _integer_series(
        candidates, "requested_quantity", "Candidate request quantity"
    )
    candidates["available_quantity"] = _integer_series(
        candidates, "available_quantity", "Candidate available quantity"
    )
    requests["priority_score"] = pd.to_numeric(
        requests["priority_score"], errors="coerce"
    )
    candidates["priority_score"] = pd.to_numeric(
        candidates["priority_score"], errors="coerce"
    )
    requests["local_scarcity_score"] = pd.to_numeric(
        requests["local_scarcity_score"], errors="coerce"
    )
    candidates["local_scarcity_score"] = pd.to_numeric(
        candidates["local_scarcity_score"], errors="coerce"
    )
    candidates["straight_line_distance_km"] = pd.to_numeric(
        candidates["straight_line_distance_km"], errors="coerce"
    )

    if requests["alert_id"].isna().any() or requests.duplicated(
        ["alert_id", "requested_resource_type"]
    ).any():
        raise ValueError("Requests contain blank or duplicate alert/type keys")
    if supply["resource_id"].isna().any() or supply["resource_id"].duplicated().any():
        raise ValueError("Supply contains blank or duplicate resource IDs")
    if (requests["requested_quantity"] <= 0).any():
        raise ValueError("Requested quantities must be positive")
    if (supply["available_count"] <= 0).any():
        raise ValueError("Supply input should contain available resources only")
    if (
        requests["priority_score"].isna().any()
        or (requests["priority_score"] < 0).any()
        or (requests["priority_score"] > 1).any()
    ):
        raise ValueError("Priority scores must be numeric values between 0 and 1")
    if (
        requests["local_scarcity_score"].isna().any()
        or (requests["local_scarcity_score"] < 0).any()
        or (requests["local_scarcity_score"] > 1).any()
    ):
        raise ValueError("Local scarcity scores must be numeric values between 0 and 1")
    if (
        candidates["local_scarcity_score"].isna().any()
        or (candidates["local_scarcity_score"] < 0).any()
        or (candidates["local_scarcity_score"] > 1).any()
    ):
        raise ValueError("Candidate scarcity scores must be numeric values between 0 and 1")
    if (
        candidates["straight_line_distance_km"].isna().any()
        or (candidates["straight_line_distance_km"] < 0).any()
    ):
        raise ValueError("Candidate distances must be present and nonnegative")
    if candidates.duplicated(
        ["alert_id", "requested_resource_type", "resource_id"]
    ).any():
        raise ValueError("Candidates contain duplicate alert/resource pairs")

    request_keys = set(zip(
        requests["alert_id"], requests["requested_resource_type"]
    ))
    candidate_keys = set(zip(
        candidates["alert_id"], candidates["requested_resource_type"]
    ))
    if request_keys != candidate_keys:
        raise ValueError(
            "Candidate request keys do not exactly cover the request table"
        )

    request_values = requests.set_index(
        ["alert_id", "requested_resource_type"]
    )[["requested_quantity", "priority_score", "local_scarcity_score"]]
    request_join = candidates.merge(
        request_values.reset_index(),
        on=["alert_id", "requested_resource_type"],
        how="left",
        suffixes=("_candidate", "_request"),
        validate="many_to_one",
    )
    if (
        (request_join["requested_quantity_candidate"]
         != request_join["requested_quantity_request"]).any()
        or (request_join["priority_score_candidate"]
            - request_join["priority_score_request"]).abs().gt(1e-9).any()
        or (request_join["local_scarcity_score_candidate"]
            - request_join["local_scarcity_score_request"]).abs().gt(1e-9).any()
    ):
        raise ValueError("Candidate request values or scarcity disagree with request input")

    supply_index = supply.set_index("resource_id")
    if not candidates["resource_id"].isin(supply_index.index).all():
        raise ValueError("A candidate refers to a resource absent from supply")
    expected_types = candidates["resource_id"].map(supply_index["resource_type"])
    expected_quantities = candidates["resource_id"].map(supply_index["available_count"])
    if not (candidates["candidate_resource_type"] == expected_types).all():
        raise ValueError("Candidate resource type disagrees with supply")
    if not (candidates["available_quantity"] == expected_quantities).all():
        raise ValueError("Candidate availability disagrees with supply")

    allocations_by_candidate = {index: 0 for index in candidates.index}
    solver_results = []
    for resource_type in sorted(requests["requested_resource_type"].unique()):
        type_requests = requests[
            requests["requested_resource_type"] == resource_type
        ]
        type_candidates = candidates[
            candidates["requested_resource_type"] == resource_type
        ]
        if type_candidates.empty:
            raise ValueError(
                "No candidates for requested resource type {}".format(resource_type)
            )

        model = cp_model.CpModel()
        variables = {}
        priority_coefficients = {}
        alert_priority_coefficients = {}
        scarcity_coefficients = {}
        distance_costs = {}
        request_candidate_indices = defaultdict(list)
        resource_candidate_indices = defaultdict(list)

        for index, row in type_candidates.iterrows():
            upper_bound = min(
                int(row["requested_quantity"]), int(row["available_quantity"])
            )
            variables[index] = model.NewIntVar(
                0, upper_bound, "assign_{}".format(index)
            )
            alert_priority_coefficients[index] = int(round(
                float(row["priority_score"]) * PRIORITY_SCALE
            ))
            scarcity_coefficients[index] = int(round(
                float(row["local_scarcity_score"]) * PRIORITY_SCALE
            ))
            priority_coefficients[index] = max(
                1,
                int(round(
                    ALERT_PRIORITY_WEIGHT
                    * alert_priority_coefficients[index]
                    + LOCAL_SCARCITY_WEIGHT * scarcity_coefficients[index]
                )),
            )
            distance_costs[index] = int(round(
                float(row["straight_line_distance_km"]) * DISTANCE_SCALE
            ))
            request_candidate_indices[(
                row["alert_id"], row["requested_resource_type"]
            )].append(index)
            resource_candidate_indices[row["resource_id"]].append(index)

        for _, request in type_requests.iterrows():
            key = (request["alert_id"], request["requested_resource_type"])
            indices = request_candidate_indices.get(key, [])
            if not indices:
                raise ValueError("Request {} has no resource candidates".format(key))
            model.Add(
                sum(variables[index] for index in indices)
                <= int(request["requested_quantity"])
            )

        for resource_id, indices in resource_candidate_indices.items():
            capacity = int(supply_index.loc[resource_id, "available_count"])
            model.Add(
                sum(variables[index] for index in indices) <= capacity
            )

        priority_objective = sum(
            priority_coefficients[index] * variables[index]
            for index in variables
        )
        model.Maximize(priority_objective)

        first_solver = cp_model.CpSolver()
        first_solver.parameters.max_time_in_seconds = max_time_seconds
        first_solver.parameters.num_search_workers = 1
        first_status = first_solver.Solve(model)
        if first_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(
                "CP-SAT could not find an allocation for {}: {}".format(
                    resource_type, first_solver.StatusName(first_status)
                )
            )
        best_priority_value = sum(
            priority_coefficients[index] * first_solver.Value(variables[index])
            for index in variables
        )

        model.Add(priority_objective == best_priority_value)
        distance_objective = sum(
            distance_costs[index] * variables[index]
            for index in variables
        )
        model.Minimize(distance_objective)

        second_solver = cp_model.CpSolver()
        second_solver.parameters.max_time_in_seconds = max_time_seconds
        second_solver.parameters.num_search_workers = 1
        second_status = second_solver.Solve(model)
        if second_status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            raise RuntimeError(
                "CP-SAT could not optimize proximity for {}: {}".format(
                    resource_type, second_solver.StatusName(second_status)
                )
            )

        for index, variable in variables.items():
            allocations_by_candidate[index] = second_solver.Value(variable)
        allocated_priority_value = sum(
            alert_priority_coefficients[index]
            * second_solver.Value(variables[index])
            for index in variables
        )
        allocated_scarcity_value = sum(
            scarcity_coefficients[index]
            * second_solver.Value(variables[index])
            for index in variables
        )
        solver_results.append({
            "resource_type": resource_type,
            "priority_stage_status": first_solver.StatusName(first_status),
            "distance_stage_status": second_solver.StatusName(second_status),
            "combined_priority_scarcity_units": best_priority_value,
            "alert_priority_weighted_units": allocated_priority_value,
            "scarcity_weighted_units": allocated_scarcity_value,
            "total_distance_cost_m": int(round(second_solver.ObjectiveValue())),
        })

    candidate_allocations = candidates.copy()
    candidate_allocations["allocated_quantity"] = pd.Series(
        allocations_by_candidate
    ).astype(int)
    allocation_columns = [
        "alert_id", "requested_resource_type", "district", "GN_division",
        "priority_score", "priority_rank", "local_scarcity_score",
        "requested_quantity", "resource_id",
        "resource_district", "available_quantity", "allocated_quantity",
        "straight_line_distance_km", "is_same_district",
    ]
    allocation_columns = [
        column for column in allocation_columns
        if column in candidate_allocations.columns
    ]
    allocations = candidate_allocations.loc[
        candidate_allocations["allocated_quantity"] > 0, allocation_columns
    ].copy()

    allocated_requests = allocations.groupby(
        ["alert_id", "requested_resource_type"], as_index=False
    )["allocated_quantity"].sum()
    request_results = requests.merge(
        allocated_requests,
        on=["alert_id", "requested_resource_type"],
        how="left",
        validate="one_to_one",
    )
    request_results["allocated_quantity"] = request_results[
        "allocated_quantity"
    ].fillna(0).astype(int)
    request_results["unfilled_quantity"] = (
        request_results["requested_quantity"]
        - request_results["allocated_quantity"]
    )
    request_results["fulfillment_rate"] = (
        request_results["allocated_quantity"] / request_results["requested_quantity"]
    )

    allocated_resources = allocations.groupby(
        "resource_id", as_index=False
    )["allocated_quantity"].sum()
    resource_results = supply.merge(
        allocated_resources, on="resource_id", how="left", validate="one_to_one"
    )
    resource_results["allocated_quantity"] = resource_results[
        "allocated_quantity"
    ].fillna(0).astype(int)
    resource_results["remaining_quantity"] = (
        resource_results["available_count"]
        - resource_results["allocated_quantity"]
    )

    request_usage = request_results.set_index(
        ["alert_id", "requested_resource_type"]
    )["allocated_quantity"]
    for _, row in allocations.iterrows():
        key = (row["alert_id"], row["requested_resource_type"])
        if request_usage.loc[key] > int(row["requested_quantity"]):
            raise AssertionError("Allocation exceeds request {}".format(key))
    if (resource_results["remaining_quantity"] < 0).any():
        raise AssertionError("Allocation exceeds available resource capacity")

    return {
        "allocations": allocations.reset_index(drop=True),
        "request_results": request_results,
        "resource_results": resource_results,
        "solver_results": pd.DataFrame(solver_results),
    }
