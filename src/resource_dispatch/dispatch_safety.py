"""Pre-dispatch checks against the current resource inventory."""

import pandas as pd


ALLOCATION_COLUMNS = {
    "resource_id", "requested_resource_type", "allocated_quantity",
}
INVENTORY_COLUMNS = {"resource_id", "resource_type", "available_count"}


def _require_columns(table, required, label):
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError("{} missing columns: {}".format(label, missing))


def _normalize_resource_type(series):
    return series.astype("string").str.strip().str.upper()


def validate_dispatch_plan(allocations, current_inventory):
    """Reject plans that exceed the latest recorded inventory snapshot."""
    _require_columns(allocations, ALLOCATION_COLUMNS, "Allocations")
    _require_columns(current_inventory, INVENTORY_COLUMNS, "Current inventory")

    plan = allocations[
        ["resource_id", "requested_resource_type", "allocated_quantity"]
    ].copy()
    inventory = current_inventory[
        ["resource_id", "resource_type", "available_count"]
    ].copy()

    if inventory["resource_id"].isna().any() or inventory["resource_id"].duplicated().any():
        raise ValueError("Current inventory contains blank or duplicate resource IDs")
    if plan["resource_id"].isna().any():
        raise ValueError("Dispatch plan contains a blank resource ID")

    plan["requested_resource_type"] = _normalize_resource_type(
        plan["requested_resource_type"]
    )
    inventory["resource_type"] = _normalize_resource_type(
        inventory["resource_type"]
    )
    plan["allocated_quantity"] = pd.to_numeric(
        plan["allocated_quantity"], errors="coerce"
    )
    inventory["available_count"] = pd.to_numeric(
        inventory["available_count"], errors="coerce"
    )

    if (
        plan["allocated_quantity"].isna().any()
        or (plan["allocated_quantity"] <= 0).any()
        or (plan["allocated_quantity"] % 1 != 0).any()
    ):
        raise ValueError("Dispatch quantities must be positive integers")
    if (
        inventory["available_count"].isna().any()
        or (inventory["available_count"] < 0).any()
        or (inventory["available_count"] % 1 != 0).any()
    ):
        raise ValueError("Current availability must contain nonnegative integers")
    if plan["requested_resource_type"].isna().any() or (
        plan["requested_resource_type"] == ""
    ).any():
        raise ValueError("Dispatch plan contains a blank resource type")

    allocated_by_resource = plan.groupby(
        "resource_id", as_index=False
    ).agg(
        allocated_quantity=("allocated_quantity", "sum"),
        requested_resource_type=("requested_resource_type", "first"),
    )
    if plan.groupby("resource_id")["requested_resource_type"].nunique().gt(1).any():
        raise ValueError("Dispatch plan assigns one resource ID to multiple resource types")

    checked = allocated_by_resource.merge(
        inventory,
        on="resource_id",
        how="left",
        validate="one_to_one",
        indicator=True,
    )
    unknown = checked["_merge"] != "both"
    if unknown.any():
        ids = checked.loc[unknown, "resource_id"].tolist()
        raise ValueError(
            "Dispatch plan references resource IDs absent from current inventory: {}".format(ids)
        )
    if (
        checked["requested_resource_type"] != checked["resource_type"]
    ).any():
        ids = checked.loc[
            checked["requested_resource_type"] != checked["resource_type"],
            "resource_id",
        ].tolist()
        raise ValueError(
            "Dispatch plan resource types disagree with current inventory: {}".format(ids)
        )
    exceeded = checked["allocated_quantity"] > checked["available_count"]
    if exceeded.any():
        details = checked.loc[
            exceeded,
            ["resource_id", "allocated_quantity", "available_count"],
        ].to_dict("records")
        raise ValueError(
            "Dispatch plan exceeds current available quantities: {}".format(details)
        )

    return checked.drop(columns="_merge").reset_index(drop=True)
