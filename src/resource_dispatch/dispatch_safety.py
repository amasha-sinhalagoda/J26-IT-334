"""Pre-dispatch validation and workbook-backed reservations."""

from contextlib import contextmanager
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import uuid

import pandas as pd


ALLOCATION_COLUMNS = {
    "alert_id", "resource_id", "requested_resource_type", "requested_quantity",
    "allocated_quantity",
}
INVENTORY_COLUMNS = {
    "resource_id", "resource_type", "district", "available_count",
}
RESERVATION_COLUMNS = [
    "reservation_id", "alert_id", "requested_resource_type", "resource_id",
    "reserved_quantity", "reserved_at",
]


def _require_columns(table, required, label):
    missing = sorted(required - set(table.columns))
    if missing:
        raise ValueError("{} missing columns: {}".format(label, missing))


def _normalize_resource_type(series):
    return series.astype("string").str.strip().str.upper()


def _integer_values(series, label, allow_zero):
    values = pd.to_numeric(series, errors="coerce")
    invalid = values.isna() | (values % 1 != 0)
    invalid |= values < 0 if allow_zero else values <= 0
    if invalid.any():
        qualifier = "nonnegative" if allow_zero else "positive"
        raise ValueError("{} must contain {} integers".format(label, qualifier))
    return values.astype("int64")


def load_reservations(path):
    """Read and validate the persistent reservation ledger, if present."""
    path = Path(path)
    if not path.exists():
        return pd.DataFrame(columns=RESERVATION_COLUMNS)
    reservations = pd.read_csv(path)
    _require_columns(reservations, set(RESERVATION_COLUMNS), "Reservation ledger")
    reservations = reservations[RESERVATION_COLUMNS].copy()
    if reservations["reservation_id"].isna().any() or reservations[
        "reservation_id"
    ].duplicated().any():
        raise ValueError("Reservation ledger has blank or duplicate reservation IDs")
    if reservations["alert_id"].isna().any() or reservations[
        "resource_id"
    ].isna().any():
        raise ValueError("Reservation ledger has blank alert or resource IDs")
    reservations["requested_resource_type"] = _normalize_resource_type(
        reservations["requested_resource_type"]
    )
    reservations["reserved_quantity"] = _integer_values(
        reservations["reserved_quantity"], "Reserved quantity", allow_zero=False
    )
    timestamps = pd.to_datetime(
        reservations["reserved_at"], errors="coerce", utc=True
    )
    if timestamps.isna().any():
        raise ValueError("Reservation ledger contains invalid reservation timestamps")
    reservations["reserved_at"] = timestamps
    return reservations


def inventory_after_reservations(current_inventory, reservations):
    """Return recorded inventory with active reservations subtracted."""
    _require_columns(current_inventory, INVENTORY_COLUMNS, "Current inventory")
    inventory = current_inventory[
        ["resource_id", "resource_type", "district", "available_count"]
    ].copy()
    if inventory["resource_id"].isna().any() or inventory[
        "resource_id"
    ].duplicated().any():
        raise ValueError("Current inventory contains blank or duplicate resource IDs")
    inventory["resource_type"] = _normalize_resource_type(
        inventory["resource_type"]
    )
    inventory["available_count"] = _integer_values(
        inventory["available_count"], "Current availability", allow_zero=True
    )

    if reservations.empty:
        inventory["reserved_quantity"] = 0
    else:
        _require_columns(
            reservations, set(RESERVATION_COLUMNS), "Reservation ledger"
        )
        reservations = reservations.copy()
        reservations["requested_resource_type"] = _normalize_resource_type(
            reservations["requested_resource_type"]
        )
        reserved = reservations.groupby(
            "resource_id", as_index=False
        ).agg(
            reserved_quantity=("reserved_quantity", "sum"),
            reserved_resource_type=("requested_resource_type", "first"),
        )
        unknown = ~reserved["resource_id"].isin(inventory["resource_id"])
        if unknown.any():
            ids = reserved.loc[unknown, "resource_id"].tolist()
            raise ValueError(
                "Reservation ledger references resources absent from inventory: {}".format(
                    ids
                )
            )
        inventory = inventory.merge(
            reserved, on="resource_id", how="left", validate="one_to_one"
        )
        inventory["reserved_quantity"] = inventory[
            "reserved_quantity"
        ].fillna(0).astype("int64")
        type_mismatch = (
            inventory["reserved_resource_type"].notna()
            & (
                inventory["reserved_resource_type"]
                != inventory["resource_type"]
            )
        )
        if type_mismatch.any():
            ids = inventory.loc[type_mismatch, "resource_id"].tolist()
            raise ValueError(
                "Reservation ledger resource types disagree with inventory: {}".format(
                    ids
                )
            )
    if inventory["reserved_quantity"].gt(inventory["available_count"]).any():
        details = inventory.loc[
            inventory["reserved_quantity"] > inventory["available_count"],
            ["resource_id", "available_count", "reserved_quantity"],
        ].to_dict("records")
        raise ValueError(
            "Existing reservations exceed current workbook availability: {}".format(
                details
            )
        )
    inventory["available_count"] -= inventory["reserved_quantity"]
    return inventory.drop(columns="reserved_quantity")


def validate_dispatch_plan(allocations, current_inventory):
    """Reject plans that exceed the latest unreserved inventory snapshot."""
    _require_columns(allocations, ALLOCATION_COLUMNS, "Allocations")
    _require_columns(current_inventory, INVENTORY_COLUMNS, "Current inventory")

    plan = allocations[
        [
            "alert_id", "resource_id", "requested_resource_type",
            "requested_quantity", "allocated_quantity",
        ]
    ].copy()
    inventory = current_inventory[
        ["resource_id", "resource_type", "available_count"]
    ].copy()
    if inventory["resource_id"].isna().any() or inventory[
        "resource_id"
    ].duplicated().any():
        raise ValueError("Current inventory contains blank or duplicate resource IDs")
    if plan[["alert_id", "resource_id"]].isna().any().any():
        raise ValueError("Dispatch plan contains a blank alert or resource ID")

    plan["requested_resource_type"] = _normalize_resource_type(
        plan["requested_resource_type"]
    )
    inventory["resource_type"] = _normalize_resource_type(
        inventory["resource_type"]
    )
    plan["requested_quantity"] = _integer_values(
        plan["requested_quantity"], "Requested quantity", allow_zero=False
    )
    plan["allocated_quantity"] = _integer_values(
        plan["allocated_quantity"], "Dispatch quantity", allow_zero=False
    )
    inventory["available_count"] = _integer_values(
        inventory["available_count"], "Current availability", allow_zero=True
    )
    if plan["requested_resource_type"].isna().any() or (
        plan["requested_resource_type"] == ""
    ).any():
        raise ValueError("Dispatch plan contains a blank resource type")

    request_totals = plan.groupby(
        ["alert_id", "requested_resource_type"], as_index=False
    ).agg(
        allocated_quantity=("allocated_quantity", "sum"),
        requested_quantity=("requested_quantity", "first"),
    )
    if (
        request_totals["allocated_quantity"]
        > request_totals["requested_quantity"]
    ).any():
        raise ValueError("Dispatch plan exceeds a request quantity")

    allocated_by_resource = plan.groupby("resource_id", as_index=False).agg(
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


@contextmanager
def _reservation_lock(path):
    lock_path = str(path) + ".lock"
    with open(lock_path, "a+b") as lock_file:
        lock_file.seek(0, os.SEEK_END)
        if lock_file.tell() == 0:
            lock_file.write(b"\0")
            lock_file.flush()
        lock_file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(lock_file.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl

            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            lock_file.seek(0)
            if os.name == "nt":
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def reserve_dispatch_plan(allocations, requests, current_inventory, ledger_path):
    """Validate and atomically reserve approved plan quantities in a CSV ledger."""
    _require_columns(
        requests,
        {"alert_id", "requested_resource_type", "requested_quantity"},
        "Requests",
    )
    if allocations.empty:
        return load_reservations(ledger_path)

    ledger_path = Path(ledger_path)
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with _reservation_lock(ledger_path):
        reservations = load_reservations(ledger_path)
        effective_inventory = inventory_after_reservations(
            current_inventory, reservations
        )
        validate_dispatch_plan(allocations, effective_inventory)

        request_keys = requests[
            ["alert_id", "requested_resource_type", "requested_quantity"]
        ].copy()
        request_keys["requested_resource_type"] = _normalize_resource_type(
            request_keys["requested_resource_type"]
        )
        request_keys["requested_quantity"] = _integer_values(
            request_keys["requested_quantity"],
            "Requested quantity",
            allow_zero=False,
        )
        if request_keys.duplicated(
            ["alert_id", "requested_resource_type"]
        ).any():
            raise ValueError("Requests contain duplicate alert/resource-type pairs")

        if reservations.empty:
            previous_request_totals = pd.DataFrame(
                columns=[
                    "alert_id", "requested_resource_type", "reserved_quantity",
                ]
            )
        else:
            previous_request_totals = reservations.groupby(
                ["alert_id", "requested_resource_type"], as_index=False
            )["reserved_quantity"].sum()
        new_request_totals = allocations.groupby(
            ["alert_id", "requested_resource_type"], as_index=False
        )["allocated_quantity"].sum()
        requested_totals = new_request_totals.merge(
            previous_request_totals,
            on=["alert_id", "requested_resource_type"],
            how="left",
            validate="one_to_one",
        ).merge(
            request_keys,
            on=["alert_id", "requested_resource_type"],
            how="left",
            validate="one_to_one",
            indicator=True,
        )
        if (requested_totals["_merge"] != "both").any():
            missing = requested_totals.loc[
                requested_totals["_merge"] != "both",
                ["alert_id", "requested_resource_type"],
            ].to_dict("records")
            raise ValueError(
                "Approved plan contains requests absent from current inputs: {}".format(
                    missing
                )
            )
        requested_totals["reserved_quantity"] = requested_totals[
            "reserved_quantity"
        ].fillna(0)
        if (
            requested_totals["allocated_quantity"]
            + requested_totals["reserved_quantity"]
            > requested_totals["requested_quantity"]
        ).any():
            raise ValueError(
                "Approved plan would reserve more than the remaining request quantity"
            )

        new_rows = allocations[
            [
                "alert_id", "requested_resource_type", "resource_id",
                "allocated_quantity",
            ]
        ].rename(columns={"allocated_quantity": "reserved_quantity"})
        new_rows["reservation_id"] = [
            str(uuid.uuid4()) for _ in range(len(new_rows))
        ]
        new_rows["reserved_at"] = datetime.now(timezone.utc).isoformat()
        new_rows = new_rows[RESERVATION_COLUMNS]
        updated = pd.concat([reservations, new_rows], ignore_index=True)

        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="",
            suffix=".tmp",
            dir=str(ledger_path.parent),
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            updated.to_csv(temp_file, index=False)
        try:
            os.replace(str(temp_path), str(ledger_path))
        except Exception:
            if temp_path.exists():
                temp_path.unlink()
            raise
        return updated
