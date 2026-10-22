from pathlib import Path
import json
import shutil
import sys

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_DIR / "Dual route optimization"
SOURCE_DATA_DIR = INPUT_DIR / "source_data"
OUTPUT_DIR = PROJECT_DIR / "processed_data" / "dual_route"
BOUNDARY_SOURCE = SOURCE_DATA_DIR / "geoBoundaries-LKA-ADM2.geojson"
NWE_LHMP_SOURCE = (
    PROJECT_DIR
    / "NuwaraEliya(SLIIT)-(Bagya)"
    / "LHZM"
    / "Nuwara_Eliya"
    / "Nuwara_Eliya_LHMP_50000"
)

TARGET_BOUNDARIES = {
    "Ratnapura District": "Ratnapura",
    "Kegalle District": "Kegalle",
    "Kalutara District": "Kalutara",
    "Badulla District": "Badulla",
    "Nuwara Eliya District": "Nuwara Eliya",
}

DISTRICTS = {
    "ratnapura": "Ratnapura",
    "kegalle": "Kegalle",
    "kalutara": "Kalutara",
    "badulla": "Badulla",
    "nuwara eliya": "Nuwara Eliya",
}
LATITUDE_RANGE = (5.8, 10.0)
LONGITUDE_RANGE = (79.4, 82.1)

DATASETS = {
    "events": {
        "file": "events.xlsx",
        "required": [
            "event_id", "scenario_id", "hazard_type", "district",
            "started_at", "ended_at", "severity",
        ],
    },
    "hazard_polygons": {
        "file": "hazard_polygons.xlsx",
        "required": [
            "hazard_id", "event_id", "scenario_id", "district",
            "hazard_type", "severity", "valid_from", "valid_to",
            "geometry_crs", "geometry_wkt",
        ],
        "geometry_type": "MULTIPOLYGON",
    },
    "incident_points": {
        "file": "incident_points.xlsx",
        "required": [
            "incident_id", "event_id", "district", "incident_type",
            "latitude", "longitude",
        ],
    },
    "lhmp_zones": {
        "file": "lhmp_zones.xlsx",
        "required": [
            "zone_id", "district", "hazard_class", "geometry_crs",
            "geometry_wkt",
        ],
        "geometry_type": "MULTIPOLYGON",
    },
    "road_closures": {
        "file": "road_closures.xlsx",
        "required": [
            "closure_id", "event_id", "district", "closure_type",
            "status", "valid_from", "valid_to", "geometry_crs",
            "geometry_wkt",
        ],
        "geometry_type": "LINESTRING",
    },
    "evacuation_origins": {
        "file": "evacuation_origins.xlsx",
        "required": [
            "origin_id", "scenario_id", "district", "origin_type",
            "latitude", "longitude",
        ],
    },
    "dispatch_facilities": {
        "file": "dispatch_facilities.xlsx",
        "required": [
            "facility_id", "facility_type", "district", "name",
            "latitude", "longitude", "operational_status",
        ],
    },
    "shelters": {
        "file": "shelters.xlsx",
        "required": [
            "shelter_id", "district", "name", "latitude", "longitude",
            "total_capacity", "available_capacity", "operational_status",
        ],
    },
}

ID_COLUMNS = {
    "events": "event_id",
    "hazard_polygons": "hazard_id",
    "incident_points": "incident_record_id",
    "lhmp_zones": "zone_id",
    "road_closures": "closure_id",
    "evacuation_origins": "origin_id",
    "dispatch_facilities": "facility_id",
    "shelters": "shelter_id",
}

DATE_COLUMNS = {
    "events": ["started_at", "ended_at"],
    "hazard_polygons": ["valid_from", "valid_to"],
    "incident_points": ["occurred_at"],
    "road_closures": ["valid_from", "valid_to"],
}


def _require_columns(frame, required, dataset):
    missing = sorted(set(required) - set(frame.columns))
    if missing:
        raise ValueError(
            "{} is missing required columns: {}".format(dataset, ", ".join(missing))
        )


def _normalize_districts(frame, dataset):
    normalized = frame["district"].astype("string").str.strip()
    mapped = normalized.str.casefold().map(DISTRICTS)
    invalid = normalized.notna() & mapped.isna()
    if invalid.any():
        values = sorted(normalized[invalid].unique().tolist())
        raise ValueError("{} has unsupported district values: {}".format(dataset, values))
    if mapped.isna().any():
        raise ValueError("{} contains blank district values".format(dataset))
    frame["district"] = mapped


def _normalize_dates(frame, columns, dataset):
    for column in columns:
        if column not in frame:
            continue
        raw = frame[column]
        parsed = pd.to_datetime(raw, errors="coerce")
        invalid = raw.notna() & parsed.isna()
        if invalid.any():
            raise ValueError(
                "{} has invalid dates in {}".format(dataset, column)
            )
        frame[column] = parsed.dt.strftime("%Y-%m-%dT%H:%M:%S")
        frame.loc[parsed.isna(), column] = pd.NA


def _validate_coordinates(frame, dataset, latitude, longitude):
    for column in (latitude, longitude):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
        if frame[column].isna().any():
            raise ValueError("{} contains missing or invalid {}".format(dataset, column))

    invalid = (
        ~frame[latitude].between(*LATITUDE_RANGE)
        | ~frame[longitude].between(*LONGITUDE_RANGE)
    )
    if invalid.any():
        rows = (frame.index[invalid] + 2).tolist()[:10]
        raise ValueError(
            "{} has coordinates outside Sri Lanka bounds at spreadsheet rows {}".format(
                dataset, rows
            )
        )


def _validate_wkt(frame, dataset, geometry_type):
    for _, row in frame.iterrows():
        value = row["geometry_wkt"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("{} contains a blank geometry_wkt".format(dataset))
        wkt = value.strip()
        if not wkt.upper().startswith(geometry_type):
            raise ValueError(
                "{} geometry must be {}, got {!r}".format(
                    dataset, geometry_type, wkt[:40]
                )
            )
        if wkt.count("(") != wkt.count(")") or wkt.count("(") == 0:
            raise ValueError("{} contains unbalanced WKT parentheses".format(dataset))

        crs = str(row["geometry_crs"]).strip().upper()
        if crs != "EPSG:5234":
            raise ValueError(
                "{} geometry must use EPSG:5234, got {!r}".format(dataset, crs)
            )


def _add_provenance(frame, dataset):
    if dataset == "events":
        official = frame["event_id"].isin({"EV-NWE-HIST", "EV-NWE-DIT"})
    elif dataset == "incident_points":
        official = frame["district"].eq("Nuwara Eliya")
    elif dataset == "evacuation_origins":
        official = (
            frame["district"].eq("Nuwara Eliya")
            & frame["scenario_id"].eq("SC-NWE-DIT")
            & frame["origin_type"].eq("HR")
        )
    else:
        official = pd.Series(False, index=frame.index)

    frame["source_type"] = official.map(
        {True: "official", False: "synthetic"}
    )
    frame["is_synthetic"] = ~official
    frame["accepted_for_prototype"] = True


def _add_incident_record_ids(frame):
    source_id = frame["incident_id"].astype("string").str.strip()
    if source_id.isna().any() or source_id.eq("").any():
        raise ValueError("incident_points contains a blank incident_id")

    sort_columns = [
        column for column in (
            "incident_id", "incident_type", "occurred_at", "latitude", "longitude"
        )
        if column in frame
    ]
    sorted_frame = frame.sort_values(sort_columns, kind="mergesort", na_position="last")
    occurrence = sorted_frame.groupby("incident_id", sort=False).cumcount() + 1
    occurrence = occurrence.reindex(frame.index)
    frame["incident_record_id"] = source_id + "-" + occurrence.map(
        lambda value: "{:02d}".format(value)
    )


def _validate_unique_ids(frame, dataset, id_column):
    if frame[id_column].isna().any() or frame[id_column].astype(str).str.strip().eq("").any():
        raise ValueError("{} contains a blank {}".format(dataset, id_column))
    duplicate = frame[id_column].astype(str).duplicated(keep=False)
    if duplicate.any():
        examples = frame.loc[duplicate, id_column].astype(str).unique()[:10].tolist()
        raise ValueError(
            "{} contains duplicate {} values: {}".format(
                dataset, id_column, examples
            )
        )


def _validate_references(tables):
    events = tables["events"]
    event_ids = set(events["event_id"].astype(str))
    scenarios = set(events["scenario_id"].astype(str))
    event_by_id = events.set_index("event_id")

    for dataset in ("hazard_polygons", "incident_points", "road_closures"):
        frame = tables[dataset]
        if "event_id" not in frame:
            continue
        unknown = sorted(set(frame["event_id"].dropna().astype(str)) - event_ids)
        if unknown:
            raise ValueError("{} references unknown events: {}".format(dataset, unknown[:10]))
        if dataset in {"hazard_polygons", "road_closures"}:
            for _, row in frame.iterrows():
                event = event_by_id.loc[row["event_id"]]
                if row["district"] != event["district"]:
                    raise ValueError(
                        "{} {} district does not match its event".format(
                            dataset, row[ID_COLUMNS[dataset]]
                        )
                    )
                if (
                    dataset == "hazard_polygons"
                    and row["scenario_id"] != event["scenario_id"]
                ):
                    raise ValueError(
                        "Hazard {} scenario does not match its event".format(
                            row["hazard_id"]
                        )
                    )
                if dataset == "hazard_polygons" and row["hazard_type"] != event["hazard_type"]:
                    raise ValueError(
                        "Hazard {} type does not match its event".format(row["hazard_id"])
                    )

    origins = tables["evacuation_origins"]
    unknown_scenarios = sorted(
        set(origins["scenario_id"].dropna().astype(str)) - scenarios
    )
    if unknown_scenarios:
        raise ValueError(
            "evacuation_origins references unknown scenarios: {}".format(
                unknown_scenarios[:10]
            )
        )


def _validate_tables(tables):
    _add_incident_record_ids(tables["incident_points"])

    for dataset, frame in tables.items():
        _normalize_districts(frame, dataset)
        _validate_unique_ids(frame, dataset, ID_COLUMNS[dataset])
        if "latitude" in frame and "longitude" in frame:
            _validate_coordinates(frame, dataset, "latitude", "longitude")
        if "centroid_lat" in frame and "centroid_lon" in frame:
            _validate_coordinates(frame, dataset, "centroid_lat", "centroid_lon")
        _normalize_dates(frame, DATE_COLUMNS.get(dataset, []), dataset)
        _add_provenance(frame, dataset)

        if dataset in {"events", "hazard_polygons"}:
            frame["hazard_type"] = frame["hazard_type"].astype("string").str.strip().str.casefold()
            if not frame["hazard_type"].isin({"flood", "landslide"}).all():
                raise ValueError("{} has an unsupported hazard_type".format(dataset))
        if dataset == "events":
            frame["severity"] = pd.to_numeric(frame["severity"], errors="coerce")
            if not frame["severity"].dropna().between(1, 4).all():
                raise ValueError("events severity must be between 1 and 4 when provided")
            starts = pd.to_datetime(frame["started_at"], errors="coerce")
            ends = pd.to_datetime(frame["ended_at"], errors="coerce")
            if starts.isna().any() or ends.isna().any() or (starts > ends).any():
                raise ValueError("events require valid windows with started_at <= ended_at")
        if dataset == "hazard_polygons":
            frame["severity"] = pd.to_numeric(frame["severity"], errors="coerce")
            if not frame["severity"].between(1, 4).all():
                raise ValueError("hazard_polygons severity must be between 1 and 4")
            starts = pd.to_datetime(frame["valid_from"], errors="coerce")
            ends = pd.to_datetime(frame["valid_to"], errors="coerce")
            if starts.isna().any() or ends.isna().any() or (starts > ends).any():
                raise ValueError(
                    "hazard_polygons require valid windows with valid_from <= valid_to"
                )
            _validate_wkt(frame, dataset, DATASETS[dataset]["geometry_type"])
        if dataset == "lhmp_zones":
            frame["hazard_class"] = pd.to_numeric(frame["hazard_class"], errors="coerce")
            if not frame["hazard_class"].isin({1, 2, 3, 4}).all():
                raise ValueError("lhmp_zones hazard_class must be one of 1, 2, 3, 4")
            _validate_wkt(frame, dataset, DATASETS[dataset]["geometry_type"])
        if dataset == "road_closures":
            frame["closure_type"] = frame["closure_type"].astype("string").str.strip().str.casefold()
            frame["status"] = frame["status"].astype("string").str.strip().str.casefold()
            if not frame["closure_type"].isin({"road", "bridge"}).all():
                raise ValueError("road_closures closure_type must be road or bridge")
            if not frame["status"].isin({"closed", "restricted", "reopened"}).all():
                raise ValueError("road_closures has an unsupported status")
            starts = pd.to_datetime(frame["valid_from"], errors="coerce")
            ends = pd.to_datetime(frame["valid_to"], errors="coerce")
            if starts.isna().any() or ends.isna().any() or (starts > ends).any():
                raise ValueError(
                    "road_closures require valid windows with valid_from <= valid_to"
                )
            _validate_wkt(frame, dataset, DATASETS[dataset]["geometry_type"])
        if dataset == "evacuation_origins":
            frame["origin_type"] = frame["origin_type"].astype("string").str.strip().str.upper()
            if not frame["origin_type"].isin({"GN", "HR"}).all():
                raise ValueError("evacuation_origins origin_type must be GN or HR")
        if dataset == "dispatch_facilities":
            frame["facility_type"] = frame["facility_type"].astype("string").str.strip()
            if not frame["facility_type"].isin({"DDMC_station", "hospital"}).all():
                raise ValueError("dispatch_facilities has an unsupported facility_type")
            frame["operational_status"] = (
                frame["operational_status"].astype("string").str.strip().str.casefold()
            )
            if not frame["operational_status"].isin({"operational", "limited"}).all():
                raise ValueError("dispatch_facilities has an unsupported operational_status")
        if dataset == "shelters":
            for column in ("total_capacity", "available_capacity"):
                frame[column] = pd.to_numeric(frame[column], errors="coerce")
                if frame[column].isna().any() or (frame[column] < 0).any():
                    raise ValueError("shelters {} must be non-negative".format(column))
            if (frame["available_capacity"] > frame["total_capacity"]).any():
                raise ValueError("shelters available_capacity exceeds total_capacity")
            frame["operational_status"] = (
                frame["operational_status"].astype("string").str.strip().str.casefold()
            )
            if not frame["operational_status"].isin({"open", "full", "closed"}).all():
                raise ValueError("shelters has an unsupported operational_status")
            unavailable = frame["operational_status"].isin({"full", "closed"})
            if (frame.loc[unavailable, "available_capacity"] != 0).any():
                raise ValueError("full or closed shelters must have zero available_capacity")

    _validate_references(tables)


def load_routing_tables(input_dir=INPUT_DIR):
    tables = {}
    for dataset, config in DATASETS.items():
        path = Path(input_dir) / config["file"]
        if not path.is_file():
            raise FileNotFoundError("Required routing dataset not found: {}".format(path))
        frame = pd.read_excel(path, sheet_name=0)
        frame.columns = [str(column).strip() for column in frame.columns]
        _require_columns(frame, config["required"], dataset)
        tables[dataset] = frame

    _validate_tables(tables)
    return tables


def write_preprocessed_data(tables, output_dir=OUTPUT_DIR):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    for dataset, frame in tables.items():
        frame.to_csv(output_dir / "{}.csv".format(dataset), index=False)

    source_collection, boundary_features = _select_district_boundaries(BOUNDARY_SOURCE)
    boundary_collection = {
        key: value for key, value in source_collection.items()
        if key != "features"
    }
    boundary_collection["type"] = "FeatureCollection"
    boundary_collection["features"] = []
    for feature, district in boundary_features:
        feature = dict(feature)
        feature["properties"] = dict(feature.get("properties", {}))
        feature["properties"]["district"] = district
        boundary_collection["features"].append(feature)
    (output_dir / "district_boundaries.geojson").write_text(
        json.dumps(boundary_collection, ensure_ascii=False),
        encoding="utf-8",
    )

    lhmp_output_dir = output_dir / "nuwara_eliya_lhmp"
    lhmp_output_dir.mkdir(parents=True, exist_ok=True)
    for extension in (".shp", ".shx", ".dbf", ".prj", ".cpg"):
        source = NWE_LHMP_SOURCE.with_suffix(extension)
        if not source.is_file():
            raise FileNotFoundError(
                "Nuwara Eliya NBRI LHMP component not found: {}".format(source)
            )
        shutil.copy2(source, lhmp_output_dir / source.name)

    report_lines = [
        "Dual-route input preprocessing report",
        "======================================",
        "Source: {}".format(INPUT_DIR),
        "Outputs: {}".format(output_dir),
        "Coordinate validation bounds: latitude {}, longitude {}".format(
            LATITUDE_RANGE, LONGITUDE_RANGE
        ),
        "WKT layers retain EPSG:5234 and original geometry_wkt values.",
        "Point coordinates retain WGS84 latitude/longitude values.",
        "",
        "Dataset row counts and provenance:",
    ]
    for dataset, frame in tables.items():
        provenance = frame["source_type"].value_counts().to_dict()
        report_lines.append(
            "- {}: {} rows (official={}, synthetic={})".format(
                dataset,
                len(frame),
                provenance.get("official", 0),
                provenance.get("synthetic", 0),
            )
        )

    report_lines.extend([
        "",
        "Interpretation and limitations:",
        "- All supplied rows were retained and accepted as prototype inputs; source_type and is_synthetic describe documented provenance, not inclusion/exclusion.",
        "- Accepted scenario, hazard, and closure rows remain scenario inputs; they must not be represented as independently verified operational closure evidence.",
        "- road_closures has no OSM way IDs; spatial matching to the road graph is still required.",
        "- lhmp_zones.xlsx covers Ratnapura, Kegalle, Kalutara, and Badulla; the Nuwara Eliya NBRI shapefile is copied alongside the prepared tables.",
        "- district_boundaries.geojson contains the five requested ADM2 boundaries in the source GeoJSON CRS (WGS84); verify the source and boundary alignment before clipping the graph.",
        "- CSV preserves WKT and CRS metadata but does not validate polygon topology or load data into PostGIS.",
        "- Official-labelled Nuwara Eliya incidents and Dithawa HR points retain missing source attributes as missing; no synthetic severity or population values are imputed.",
    ])
    (output_dir / "preprocessing_report.txt").write_text(
        "\n".join(report_lines) + "\n", encoding="utf-8"
    )
    return output_dir


def _select_district_boundaries(source_path=BOUNDARY_SOURCE):
    if not Path(source_path).is_file():
        raise FileNotFoundError(
            "Sri Lanka ADM2 boundary GeoJSON not found: {}".format(source_path)
        )

    with Path(source_path).open(encoding="utf-8") as source:
        collection = json.load(source)

    features_by_name = {}
    for feature in collection.get("features", []):
        name = feature.get("properties", {}).get("shapeName")
        if name in TARGET_BOUNDARIES:
            features_by_name[name] = feature

    missing = sorted(set(TARGET_BOUNDARIES) - set(features_by_name))
    if missing:
        raise ValueError(
            "ADM2 boundary source is missing target districts: {}".format(missing)
        )

    selected = [
        (features_by_name[name], TARGET_BOUNDARIES[name])
        for name in TARGET_BOUNDARIES
    ]
    source_crs = collection.get("crs", {}).get("properties", {}).get("name")
    if source_crs not in {
        "urn:ogc:def:crs:OGC:1.3:CRS84",
        "urn:ogc:def:crs:EPSG::4326",
    }:
        raise ValueError(
            "ADM2 boundary source CRS is not recognized as WGS84: {!r}".format(
                source_crs
            )
        )

    return collection, selected


def main():
    try:
        tables = load_routing_tables()
        output_dir = write_preprocessed_data(tables)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print("Dual-route preprocessing failed: {}".format(exc), file=sys.stderr)
        return 1

    print("Preprocessed {} routing tables into {}".format(len(tables), output_dir))
    print("See {}".format(output_dir / "preprocessing_report.txt"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
