"""District-level resource scarcity measures for allocation inputs."""

import numpy as np
import pandas as pd


SCARCITY_COLUMNS = [
    "district",
    "requested_resource_type",
    "local_demand_quantity",
    "local_available_quantity",
    "local_shortage_quantity",
    "local_scarcity_score",
]


def _normalize_key(series):
    return series.astype("string").str.strip().str.casefold()


def calculate_local_scarcity(requests, inventory):
    """Measure the share of local demand not covered by local available supply.

    Demand and supply are grouped by district and resource type. A score of 0
    means local availability covers demand; 1 means there is no local supply.
    Cross-district resources are deliberately excluded from this local measure.
    """
    request_required = {
        "district", "requested_resource_type", "requested_quantity",
    }
    inventory_required = {"district", "resource_type", "available_count"}
    missing_requests = sorted(request_required - set(requests.columns))
    missing_inventory = sorted(inventory_required - set(inventory.columns))
    if missing_requests:
        raise ValueError("Requests missing columns: {}".format(missing_requests))
    if missing_inventory:
        raise ValueError("Inventory missing columns: {}".format(missing_inventory))

    demand = requests[
        ["district", "requested_resource_type", "requested_quantity"]
    ].copy()
    supply = inventory[["district", "resource_type", "available_count"]].copy()
    demand["requested_quantity"] = pd.to_numeric(
        demand["requested_quantity"], errors="coerce"
    )
    supply["available_count"] = pd.to_numeric(
        supply["available_count"], errors="coerce"
    )

    if (
        demand["requested_quantity"].isna().any()
        or not np.isfinite(demand["requested_quantity"]).all()
        or (demand["requested_quantity"] <= 0).any()
    ):
        raise ValueError("Requested quantities must be finite positive numbers")
    if (
        supply["available_count"].isna().any()
        or not np.isfinite(supply["available_count"]).all()
        or (supply["available_count"] < 0).any()
    ):
        raise ValueError("Available quantities must be finite nonnegative numbers")

    demand["_district_key"] = _normalize_key(demand["district"])
    demand["_resource_type_key"] = _normalize_key(
        demand["requested_resource_type"]
    )
    supply["_district_key"] = _normalize_key(supply["district"])
    supply["_resource_type_key"] = _normalize_key(supply["resource_type"])
    if (
        demand[["_district_key", "_resource_type_key"]].isna().any().any()
        or demand[["_district_key", "_resource_type_key"]].eq("").any().any()
        or supply[["_district_key", "_resource_type_key"]].isna().any().any()
        or supply[["_district_key", "_resource_type_key"]].eq("").any().any()
    ):
        raise ValueError("District and resource type values must be present")

    demand_by_area = demand.groupby(
        ["_district_key", "_resource_type_key"], as_index=False
    ).agg(
        district=("district", "first"),
        requested_resource_type=("requested_resource_type", "first"),
        local_demand_quantity=("requested_quantity", "sum"),
    )
    supply_by_area = supply.groupby(
        ["_district_key", "_resource_type_key"], as_index=False
    ).agg(local_available_quantity=("available_count", "sum"))

    scarcity = demand_by_area.merge(
        supply_by_area,
        on=["_district_key", "_resource_type_key"],
        how="left",
        validate="one_to_one",
    )
    scarcity["local_available_quantity"] = scarcity[
        "local_available_quantity"
    ].fillna(0)
    scarcity["local_shortage_quantity"] = (
        scarcity["local_demand_quantity"]
        - scarcity["local_available_quantity"]
    ).clip(lower=0)
    scarcity["local_scarcity_score"] = (
        scarcity["local_shortage_quantity"] / scarcity["local_demand_quantity"]
    )

    return scarcity[
        [
            "_district_key", "_resource_type_key",
        ] + SCARCITY_COLUMNS
    ]
