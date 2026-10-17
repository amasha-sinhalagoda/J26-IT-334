from pathlib import Path
import re

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "processed_data"
TARGET_DISTRICTS = {
    "ratnapura": "Ratnapura",
    "kegalle": "Kegalle",
    "kalutara": "Kalutara",
    "badulla": "Badulla",
    "nuwara eliya": "Nuwara Eliya",
}

INPUT_FILES = {
    "alerts": "Alert_Requests_5Districts.xlsx",
    "resources": "Resource_Inventory_5Districts.xlsx",
    "assignments": "Dispatch_Assignments_5Districts.xlsx",
    "population": "GN_population_excel.xlsx",
}

REQUIRED_COLUMNS = {
    "alerts": {
        "alert_id", "timestamp", "hazard_type", "severity", "confidence",
        "district", "DS_division", "GN_division", "latitude", "longitude",
        "affected_population", "affected_households",
        "requested_resource_type", "requested_quantity",
    },
    "resources": {
        "resource_id", "resource_type", "district", "latitude", "longitude",
        "capacity", "offline_count", "available_count", "status",
    },
    "assignments": {
        "assignment_id", "alert_id", "resource_id", "resource_type",
        "assigned_quantity", "destination_district", "destination_GN_division",
        "destination_latitude", "destination_longitude", "status",
    },
}


def normalize_text_columns(table):
    for column in table.select_dtypes(include=["object", "string"]).columns:
        table[column] = table[column].astype("string").str.strip()
        table[column] = table[column].replace("", pd.NA)
    return table


def normalize_districts(table, columns):
    for column in columns:
        cleaned = table[column].astype("string").str.strip()
        canonical = cleaned.str.casefold().map(TARGET_DISTRICTS)
        table[column] = canonical.fillna(cleaned)


def flatten_population_columns(table):
    direct_names = {
        "province code": "province_code",
        "province name": "province_name",
        "district code": "district_code",
        "district name": "district_name",
        "ds_division code": "ds_division_code",
        "ds_division name": "ds_division_name",
        "gn_division code": "gn_division_code",
        "gn_division name": "gn_division_name",
        "gn_division number": "gn_division_number",
    }
    flattened = []
    for primary, secondary in table.columns:
        primary_clean = str(primary).replace("\n", " ").strip().casefold()
        secondary_clean = str(secondary).replace("\n", " ").strip().casefold()
        if primary_clean in direct_names:
            flattened.append(direct_names[primary_clean])
        elif primary_clean in {"sex", "age_group"}:
            suffix = re.sub(r"[^a-z0-9]+", "_", secondary_clean).strip("_")
            prefix = "sex" if primary_clean == "sex" else "age"
            flattened.append("{}_{}".format(prefix, suffix))
        else:
            flattened.append("{}_{}".format(primary_clean, secondary_clean))
    table.columns = flattened
    return table


def require_columns(name, table, errors):
    missing = sorted(REQUIRED_COLUMNS[name] - set(table.columns))
    if missing:
        errors.append("{} is missing required columns: {}".format(name, missing))


def add_nonnegative_errors(name, table, columns, errors):
    for column in columns:
        invalid = table[column].isna() | (table[column] < 0)
        if invalid.any():
            errors.append("{} has {} missing/negative values in {}".format(
                name, int(invalid.sum()), column
            ))


def main():
    missing_files = [
        filename for filename in INPUT_FILES.values()
        if not (BASE_DIR / filename).exists()
    ]
    if missing_files:
        raise FileNotFoundError(
            "Missing input workbook(s): {}".format(", ".join(missing_files))
        )

    alerts = pd.read_excel(BASE_DIR / INPUT_FILES["alerts"])
    resources = pd.read_excel(BASE_DIR / INPUT_FILES["resources"])
    assignments = pd.read_excel(BASE_DIR / INPUT_FILES["assignments"])
    population = pd.read_excel(
        BASE_DIR / INPUT_FILES["population"],
        sheet_name="Population",
        header=[3, 4],
    )

    alerts = normalize_text_columns(alerts)
    resources = normalize_text_columns(resources)
    assignments = normalize_text_columns(assignments)
    population = flatten_population_columns(population)
    population = normalize_text_columns(population)

    normalize_districts(alerts, ["district"])
    normalize_districts(resources, ["district"])
    normalize_districts(
        assignments, ["origin_district", "destination_district"]
    )

    for table, column in [
        (alerts, "requested_resource_type"),
        (resources, "resource_type"),
        (assignments, "resource_type"),
    ]:
        table[column] = table[column].str.upper()

    for table, column in [
        (alerts, "timestamp"),
        (resources, "last_updated"),
        (assignments, "assignment_time"),
        (assignments, "estimated_arrival"),
        (assignments, "status_time"),
    ]:
        if column in table.columns:
            table[column] = pd.to_datetime(table[column], errors="coerce")

    numeric_columns = {
        "alerts": [
            "confidence", "latitude", "longitude", "affected_population",
            "affected_households", "requested_quantity",
        ],
        "resources": [
            "latitude", "longitude", "capacity", "offline_count",
            "available_count",
        ],
        "assignments": [
            "assigned_quantity", "destination_latitude", "destination_longitude",
        ],
    }
    tables = {"alerts": alerts, "resources": resources, "assignments": assignments}
    for name, columns in numeric_columns.items():
        for column in columns:
            tables[name][column] = pd.to_numeric(
                tables[name][column], errors="coerce"
            )

    district_column = "district_name"
    if district_column not in population.columns:
        raise ValueError("Could not identify the population district-name column")
    normalize_districts(population, [district_column])
    population_5 = population[
        population[district_column].isin(TARGET_DISTRICTS.values())
    ].copy()

    errors = []
    for name, table in tables.items():
        require_columns(name, table, errors)

    add_nonnegative_errors(
        "alerts", alerts, ["affected_population", "affected_households"], errors
    )
    add_nonnegative_errors(
        "alerts", alerts, ["requested_quantity"], errors
    )
    add_nonnegative_errors(
        "resources", resources,
        ["capacity", "offline_count", "available_count"], errors
    )
    add_nonnegative_errors(
        "assignments", assignments, ["assigned_quantity"], errors
    )

    if ((alerts["confidence"] < 0) | (alerts["confidence"] > 1)).any():
        errors.append("Alert confidence values must be between 0 and 1")
    if (
        resources["offline_count"] + resources["available_count"]
        > resources["capacity"]
    ).any():
        errors.append("Some resource counts exceed their stated capacity")

    if alerts["alert_id"].isna().any():
        errors.append("Alerts contain blank alert IDs")
    if resources["resource_id"].isna().any() or resources["resource_id"].duplicated().any():
        errors.append("Resource IDs are blank or duplicated")
    if assignments["assignment_id"].isna().any() or assignments["assignment_id"].duplicated().any():
        errors.append("Assignment IDs are blank or duplicated")
    if alerts.duplicated(["alert_id", "requested_resource_type"]).any():
        errors.append("Duplicate alert/resource-type request rows found")

    alert_ids = set(alerts["alert_id"].dropna())
    resource_by_id = resources.set_index("resource_id")
    if not assignments["alert_id"].isin(alert_ids).all():
        errors.append("Some assignments refer to alert IDs not in the alert table")
    if not assignments["resource_id"].isin(resource_by_id.index).all():
        errors.append("Some assignments refer to resource IDs not in inventory")

    known_resources = assignments["resource_id"].isin(resource_by_id.index)
    matching_types = assignments.loc[known_resources].apply(
        lambda row: row["resource_type"]
        == resource_by_id.loc[row["resource_id"], "resource_type"],
        axis=1,
    )
    if not matching_types.all():
        errors.append("Some assignment resource types do not match inventory")

    request_totals = alerts.set_index(
        ["alert_id", "requested_resource_type"]
    )["requested_quantity"]
    assigned_totals = assignments.groupby(
        ["alert_id", "resource_type"]
    )["assigned_quantity"].sum()
    for key, quantity in assigned_totals.items():
        if key not in request_totals.index or quantity > request_totals.loc[key]:
            errors.append(
                "Assigned quantity exceeds or has no matching request: {}".format(key)
            )

    OUTPUT_DIR.mkdir(exist_ok=True)
    demand_by_district = alerts.groupby(
        ["district", "requested_resource_type"], as_index=False
    ).agg(
        requested_quantity=("requested_quantity", "sum"),
        alert_count=("alert_id", "nunique"),
    )
    supply_by_district = resources.groupby(
        ["district", "resource_type"], as_index=False
    ).agg(
        available_quantity=("available_count", "sum"),
        listed_capacity=("capacity", "sum"),
        inventory_records=("resource_id", "nunique"),
    )
    demand_vs_supply = demand_by_district.merge(
        supply_by_district,
        left_on=["district", "requested_resource_type"],
        right_on=["district", "resource_type"],
        how="left",
    )
    demand_vs_supply["available_quantity"] = demand_vs_supply[
        "available_quantity"
    ].fillna(0)
    demand_vs_supply["listed_capacity"] = demand_vs_supply[
        "listed_capacity"
    ].fillna(0)
    demand_vs_supply["inventory_records"] = demand_vs_supply[
        "inventory_records"
    ].fillna(0).astype(int)
    demand_vs_supply["shortage_quantity"] = (
        demand_vs_supply["requested_quantity"]
        - demand_vs_supply["available_quantity"]
    ).clip(lower=0)
    demand_vs_supply["surplus_quantity"] = (
        demand_vs_supply["available_quantity"]
        - demand_vs_supply["requested_quantity"]
    ).clip(lower=0)
    demand_vs_supply["comparison_scope"] = (
        "Same-district synthetic snapshot; excludes cross-district reassignment and travel"
    )
    demand_vs_supply = demand_vs_supply.drop(columns=["resource_type"])

    output_tables = {
        "alerts_clean.csv": alerts,
        "resource_inventory_clean.csv": resources,
        "dispatch_assignments_clean.csv": assignments,
        "gn_population_5_districts_clean.csv": population_5,
        "district_resource_demand_vs_availability.csv": demand_vs_supply,
    }

    report_lines = [
        "Resource-aware dispatch preprocessing report",
        "Synthetic inputs: alert requests, resource inventory, and assignments.",
        "Resource coordinates are approximate DS-centre locations as labeled in source data.",
        "",
    ]
    for name, table in tables.items():
        report_lines.append("{}: {} rows, {} columns".format(name, len(table), len(table.columns)))
        missing = table.isna().sum()
        nonzero = missing[missing > 0]
        if len(nonzero):
            report_lines.append("  Missing values: {}".format(nonzero.to_dict()))
        else:
            report_lines.append("  Missing values: none")
    report_lines.extend([
        "population_5_districts: {} rows, {} columns".format(
            len(population_5), len(population_5.columns)
        ),
        "population districts: {}".format(
            sorted(population_5[district_column].dropna().unique().tolist())
        ),
        "district/resource demand comparison: {} pairs, {} shortage pairs".format(
            len(demand_vs_supply),
            int((demand_vs_supply["shortage_quantity"] > 0).sum()),
        ),
        "",
        "Validation: {}".format("PASSED" if not errors else "FAILED"),
    ])
    report_lines.extend(["- " + error for error in errors])

    report_path = OUTPUT_DIR / "preprocessing_report.txt"
    report_path.write_text("\n".join(report_lines), encoding="utf-8")
    if errors:
        raise ValueError(
            "Preprocessing validation failed; see {}".format(report_path)
        )

    for filename, table in output_tables.items():
        table.to_csv(OUTPUT_DIR / filename, index=False, encoding="utf-8-sig")

    print("Preprocessing passed.")
    print("Cleaned files and report saved to: {}".format(OUTPUT_DIR))
    print("Population rows retained: {}".format(len(population_5)))
    print("Population districts: {}".format(
        sorted(population_5[district_column].dropna().unique().tolist())
    ))


if __name__ == "__main__":
    main()
