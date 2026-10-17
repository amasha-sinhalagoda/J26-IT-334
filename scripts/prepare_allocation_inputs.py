from pathlib import Path
import sys

import numpy as np
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]

sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch.scarcity import SCARCITY_COLUMNS, calculate_local_scarcity


PROCESSED_DIR = PROJECT_DIR / "processed_data"
OUTPUT_DIR = PROCESSED_DIR / "allocation"
REQUESTS_FILE = PROCESSED_DIR / "alert_requests_prioritized.csv"
INVENTORY_FILE = PROCESSED_DIR / "resource_inventory_clean.csv"
EARTH_RADIUS_KM = 6371.0088

REQUEST_COLUMNS = [
    "alert_id", "timestamp", "district", "DS_division", "GN_division",
    "latitude", "longitude", "hazard_type", "severity", "confidence",
    "affected_population", "affected_households", "requested_resource_type",
    "requested_quantity", "priority_score", "priority_rank",
]

SUPPLY_COLUMNS = [
    "resource_id", "resource_type", "station_name", "district", "DS_division",
    "GN_division", "latitude", "longitude", "coordinate_source", "capacity",
    "offline_count", "available_count", "unit", "status", "last_updated",
]


def haversine_km(lat1, lon1, lat2, lon2):
    lat1_rad = np.radians(lat1)
    lon1_rad = np.radians(lon1)
    lat2_rad = np.radians(lat2)
    lon2_rad = np.radians(lon2)
    delta_lat = lat2_rad - lat1_rad
    delta_lon = lon2_rad - lon1_rad
    hav = (
        np.sin(delta_lat / 2.0) ** 2
        + np.cos(lat1_rad) * np.cos(lat2_rad)
        * np.sin(delta_lon / 2.0) ** 2
    )
    hav = np.clip(hav, 0.0, 1.0)
    return 2.0 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(hav))


def require_columns(table, expected, name):
    missing = sorted(set(expected) - set(table.columns))
    if missing:
        raise ValueError("{} missing columns: {}".format(name, missing))


def main():
    if not REQUESTS_FILE.exists() or not INVENTORY_FILE.exists():
        raise FileNotFoundError(
            "Run preprocess_dispatch.py and build_alert_priorities.py first"
        )

    requests = pd.read_csv(REQUESTS_FILE)
    inventory = pd.read_csv(INVENTORY_FILE)
    require_columns(requests, REQUEST_COLUMNS, "Prioritized requests")
    require_columns(inventory, SUPPLY_COLUMNS, "Resource inventory")

    requests = requests[REQUEST_COLUMNS].copy()
    requests["requested_resource_type"] = (
        requests["requested_resource_type"].astype("string").str.strip().str.upper()
    )
    requests["requested_quantity"] = pd.to_numeric(
        requests["requested_quantity"], errors="coerce"
    )
    requests["priority_score"] = pd.to_numeric(
        requests["priority_score"], errors="coerce"
    )
    requests["priority_rank"] = pd.to_numeric(
        requests["priority_rank"], errors="coerce"
    )
    requests["latitude"] = pd.to_numeric(requests["latitude"], errors="coerce")
    requests["longitude"] = pd.to_numeric(requests["longitude"], errors="coerce")

    inventory = inventory[SUPPLY_COLUMNS].copy()
    inventory["resource_type"] = (
        inventory["resource_type"].astype("string").str.strip().str.upper()
    )
    for column in ["latitude", "longitude", "available_count", "capacity"]:
        inventory[column] = pd.to_numeric(inventory[column], errors="coerce")

    if requests["alert_id"].isna().any():
        raise ValueError("Requests contain blank alert IDs")
    if requests.duplicated(["alert_id", "requested_resource_type"]).any():
        raise ValueError("Duplicate alert/resource-type request rows")
    if requests[["requested_quantity", "priority_score", "priority_rank"]].isna().any().any():
        raise ValueError("Requests have missing quantities or priority scores")
    if (requests["requested_quantity"] <= 0).any():
        raise ValueError("Requested quantities must be positive")
    if requests[["latitude", "longitude"]].isna().any().any():
        raise ValueError("Some request locations have missing coordinates")
    if requests[["district", "requested_resource_type"]].isna().any().any():
        raise ValueError("Requests must have a district and resource type")
    if (inventory["available_count"].isna().any()
            or (inventory["available_count"] < 0).any()):
        raise ValueError("Inventory availability must be present and nonnegative")

    available_supply = inventory[
        inventory["available_count"].fillna(0) > 0
    ].copy()
    if available_supply["resource_id"].isna().any():
        raise ValueError("Available inventory has blank resource IDs")
    if available_supply["resource_id"].duplicated().any():
        raise ValueError("Available inventory has duplicate resource IDs")
    if available_supply[["latitude", "longitude"]].isna().any().any():
        raise ValueError("Available resources have missing coordinates")

    scarcity = calculate_local_scarcity(requests, inventory)
    requests["_district_key"] = requests["district"].astype("string").str.strip().str.casefold()
    requests["_resource_type_key"] = requests[
        "requested_resource_type"
    ].astype("string").str.strip().str.casefold()
    requests = requests.merge(
        scarcity[
            [
                "_district_key", "_resource_type_key",
            ] + [
                "local_demand_quantity", "local_available_quantity",
                "local_shortage_quantity", "local_scarcity_score",
            ]
        ],
        on=["_district_key", "_resource_type_key"],
        how="left",
        validate="many_to_one",
    ).drop(columns=["_district_key", "_resource_type_key"])

    requested_types = set(requests["requested_resource_type"].dropna())
    supplied_types = set(available_supply["resource_type"].dropna())
    unavailable_types = sorted(requested_types - supplied_types)

    supply_for_join = available_supply.rename(
        columns={
            "resource_type": "candidate_resource_type",
            "district": "resource_district",
            "DS_division": "resource_DS_division",
            "GN_division": "resource_GN_division",
            "latitude": "resource_latitude",
            "longitude": "resource_longitude",
            "available_count": "available_quantity",
            "status": "resource_status",
            "last_updated": "inventory_last_updated",
        }
    )

    candidates = requests.merge(
        supply_for_join,
        left_on="requested_resource_type",
        right_on="candidate_resource_type",
        how="left",
        validate="many_to_many",
    )
    candidates = candidates.dropna(subset=["resource_id"]).copy()
    candidates["is_same_district"] = (
        candidates["district"].astype("string").str.casefold()
        == candidates["resource_district"].astype("string").str.casefold()
    )
    candidates["straight_line_distance_km"] = haversine_km(
        candidates["latitude"].to_numpy(),
        candidates["longitude"].to_numpy(),
        candidates["resource_latitude"].to_numpy(),
        candidates["resource_longitude"].to_numpy(),
    )
    candidates["candidate_rank_by_distance"] = candidates.groupby(
        ["alert_id", "requested_resource_type"]
    )["straight_line_distance_km"].rank(method="first").astype(int)
    candidates["distance_basis"] = "Straight-line estimate; not road travel distance"

    request_keys = set(zip(
        requests["alert_id"], requests["requested_resource_type"]
    ))
    candidate_keys = set(zip(
        candidates["alert_id"], candidates["requested_resource_type"]
    ))
    uncovered_requests = sorted(request_keys - candidate_keys)
    if unavailable_types or uncovered_requests:
        raise ValueError(
            "Some requests have no compatible available supply. Types: {}; requests: {}".format(
                unavailable_types, uncovered_requests
            )
        )
    if candidates["resource_id"].isna().any():
        raise ValueError("Candidate table contains a blank resource ID")
    if (candidates["available_quantity"] <= 0).any():
        raise ValueError("Candidate table contains unavailable resources")
    if (
        candidates["straight_line_distance_km"].isna().any()
        or (candidates["straight_line_distance_km"] < 0).any()
    ):
        raise ValueError("Candidate distance calculation produced invalid values")
    if candidates.duplicated(
        ["alert_id", "requested_resource_type", "resource_id"]
    ).any():
        raise ValueError("Duplicate alert/resource candidate pairs")

    candidates = candidates.sort_values(
        ["priority_rank", "candidate_rank_by_distance", "alert_id"]
    ).reset_index(drop=True)
    available_supply = available_supply.sort_values(
        ["resource_type", "district", "resource_id"]
    ).reset_index(drop=True)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    requests.to_csv(OUTPUT_DIR / "allocation_requests.csv", index=False, encoding="utf-8-sig")
    available_supply.to_csv(
        OUTPUT_DIR / "available_resource_supply.csv", index=False, encoding="utf-8-sig"
    )
    candidates.to_csv(
        OUTPUT_DIR / "allocation_candidates.csv", index=False, encoding="utf-8-sig"
    )
    scarcity[SCARCITY_COLUMNS].to_csv(
        OUTPUT_DIR / "district_resource_scarcity.csv",
        index=False,
        encoding="utf-8-sig",
    )

    notes = [
        "Allocation input preparation",
        "Requests come from the supplied alert dataset and inherit the prototype priority scores.",
        "Supply uses the available_count values recorded in the resource inventory workbook.",
        "Local scarcity score = max(local demand - local available supply, 0) / local demand.",
        "Scarcity is measured by district and resource type; cross-district supply is excluded from the score.",
        "The score is an allocation input diagnostic only; the current optimizer does not yet use it.",
        "Candidates pair each request with every available inventory record of the same resource type.",
        "Cross-district resources are included; the optimization stage must enforce resource capacity across requests.",
        "straight_line_distance_km is only a proximity proxy, not road travel time or a safe route.",
        "Resource coordinates are labeled as approximate DS-centre locations in the source workbook.",
        "A future routing stage should replace this proxy with road-network travel costs and hazard closures.",
        "Requested resource types without any available supply: {}".format(
            unavailable_types if unavailable_types else "none"
        ),
        "Request rows: {}".format(len(requests)),
        "Available inventory records: {}".format(len(available_supply)),
        "Compatible candidate pairs: {}".format(len(candidates)),
        "Same-district candidate pairs: {}".format(int(candidates["is_same_district"].sum())),
        "Cross-district candidate pairs: {}".format(int((~candidates["is_same_district"]).sum())),
    ]
    (OUTPUT_DIR / "allocation_input_notes.txt").write_text(
        "\n".join(notes), encoding="utf-8"
    )

    print("Allocation inputs prepared and validated.")
    print("Request rows: {}".format(len(requests)))
    print("Available inventory records: {}".format(len(available_supply)))
    print("Compatible candidate pairs: {}".format(len(candidates)))
    print("District/resource scarcity rows: {}".format(len(scarcity)))
    print("Output folder: {}".format(OUTPUT_DIR))


if __name__ == "__main__":
    main()
