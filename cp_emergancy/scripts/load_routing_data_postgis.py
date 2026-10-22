import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys
import uuid
import warnings

import geopandas as gpd
import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


PROJECT_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_DIR / "processed_data" / "dual_route"
ROAD_GRAPH_DIR = INPUT_DIR / "road_graph"
GRAPH_GPKG = ROAD_GRAPH_DIR / "five_districts_rda.gpkg"
DATASET_TABLES = {
    "events": "events.csv",
    "hazard_polygons": "hazard_polygons.csv",
    "incident_points": "incident_points.csv",
    "lhmp_zones": "lhmp_zones.csv",
    "road_closures": "road_closures.csv",
    "evacuation_origins": "evacuation_origins.csv",
    "dispatch_facilities": "dispatch_facilities.csv",
    "shelters": "shelters.csv",
}
TARGET_SCHEMA = "dual_route"
TARGET_SRID = 5234
DATABASE = "dual_route"
DATABASE_USER = "dual_route"
DATABASE_HOST = "127.0.0.1"
DATABASE_PORT = 55432
PRIMARY_KEYS = {
    "road_edges": ["edge_id"],
    "road_nodes": ["osmid"],
    "district_boundaries": ["shapeID"],
    "events": ["event_id"],
    "hazard_polygons": ["hazard_id"],
    "incident_points": ["incident_record_id"],
    "lhmp_zones": ["zone_id"],
    "road_closures": ["closure_id"],
    "evacuation_origins": ["origin_id"],
    "dispatch_facilities": ["facility_id"],
    "shelters": ["shelter_id"],
    "rda_crosswalk": ["osm_ref"],
}
DATE_COLUMNS = {
    "events": ("started_at", "ended_at"),
    "hazard_polygons": ("valid_from", "valid_to"),
    "incident_points": ("occurred_at",),
    "road_closures": ("valid_from", "valid_to"),
}
POINT_TABLES = (
    "incident_points",
    "evacuation_origins",
    "dispatch_facilities",
    "shelters",
)
WKT_TABLES = {
    "hazard_polygons": ("geometry_wkt", "EPSG:5234"),
    "lhmp_zones": ("geometry_wkt", "EPSG:5234"),
    "road_closures": ("geometry_wkt", "EPSG:5234"),
}


def database_url():
    return URL.create(
        "postgresql+psycopg2",
        username=os.getenv("ROUTING_DB_USER", DATABASE_USER),
        password=os.getenv("ROUTING_DB_PASSWORD"),
        host=os.getenv("ROUTING_DB_HOST", DATABASE_HOST),
        port=int(os.getenv("ROUTING_DB_PORT", DATABASE_PORT)),
        database=os.getenv("ROUTING_DB_NAME", DATABASE),
    )


def _check_inputs(input_dir=INPUT_DIR, graph_gpkg=GRAPH_GPKG):
    input_dir = Path(input_dir)
    required = [Path(graph_gpkg)]
    required.extend(input_dir / file_name for file_name in DATASET_TABLES.values())
    required.append(ROAD_GRAPH_DIR / "rda_crosswalk.csv")
    required.append(
        input_dir / "nuwara_eliya_lhmp" / "Nuwara_Eliya_LHMP_50000.shp"
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError(
            "Required prepared routing input(s) are missing: {}".format(
                ", ".join(missing)
            )
        )


def _read_csv(dataset, input_dir=INPUT_DIR):
    frame = pd.read_csv(Path(input_dir) / DATASET_TABLES[dataset])
    for column in DATE_COLUMNS.get(dataset, ()):
        frame[column] = pd.to_datetime(frame[column], errors="raise")
    return frame


def _read_wkt_layer(dataset, input_dir=INPUT_DIR):
    from shapely import from_wkt

    frame = _read_csv(dataset, input_dir)
    geometry_column, expected_crs = WKT_TABLES[dataset]
    if "geometry_crs" not in frame:
        raise ValueError("{} is missing geometry_crs".format(dataset))
    declared_crs = set(
        frame["geometry_crs"].dropna().astype(str).str.strip().str.upper()
    )
    if declared_crs != {expected_crs.upper()}:
        raise ValueError(
            "{} declares unexpected geometry CRS values: {}".format(
                dataset, sorted(declared_crs)
            )
        )
    if not frame[geometry_column].notna().all():
        raise ValueError("{} contains a missing {}".format(dataset, geometry_column))
    geometries = from_wkt(frame[geometry_column].astype(str).to_numpy())
    if any(geometry is None or geometry.is_empty for geometry in geometries):
        raise ValueError("{} contains an empty or invalid WKT geometry".format(dataset))
    frame = frame.drop(columns=[geometry_column])
    frame["geometry"] = geometries
    return gpd.GeoDataFrame(frame, geometry="geometry", crs=expected_crs)


def _read_point_layer(dataset, input_dir=INPUT_DIR):
    from shapely import points

    frame = _read_csv(dataset, input_dir)
    for column in ("latitude", "longitude"):
        frame[column] = pd.to_numeric(frame[column], errors="raise")
        if frame[column].isna().any():
            raise ValueError("{} has missing {}".format(dataset, column))
    geometry = points(
        frame["longitude"].to_numpy(),
        frame["latitude"].to_numpy(),
    )
    frame["geometry"] = geometry
    return gpd.GeoDataFrame(frame, geometry="geometry", crs="EPSG:4326").to_crs(
        epsg=TARGET_SRID
    )


def _matches_target_projection(source_crs, target_crs):
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="You will likely lose important projection information.*",
            category=UserWarning,
        )
        source_parameters = source_crs.to_dict()
        target_parameters = target_crs.to_dict()
    projection_parameters = (
        "proj", "lat_0", "lon_0", "k", "x_0", "y_0", "ellps", "units"
    )
    return all(
        key in source_parameters
        and key in target_parameters
        and (
            source_parameters[key] == target_parameters[key]
            if isinstance(source_parameters[key], str)
            else math.isclose(
                float(source_parameters[key]),
                float(target_parameters[key]),
                rel_tol=0.0,
                abs_tol=1e-8,
            )
        )
        for key in projection_parameters
    )


def _read_lhmp_zones(input_dir=INPUT_DIR):
    synthetic_zones = _read_wkt_layer("lhmp_zones", input_dir)
    path = (
        Path(input_dir)
        / "nuwara_eliya_lhmp"
        / "Nuwara_Eliya_LHMP_50000.shp"
    )
    nwe = gpd.read_file(path)
    if nwe.crs is None:
        raise ValueError("Nuwara Eliya NBRI LHMP shapefile has no CRS")
    target_crs = gpd.GeoSeries([], crs="EPSG:{}".format(TARGET_SRID)).crs
    if not _matches_target_projection(nwe.crs, target_crs):
        raise ValueError(
            "Nuwara Eliya LHMP CRS is not the expected Kandawala / EPSG:{} "
            "projection: {}".format(
                TARGET_SRID, nwe.crs
            )
        )
    nwe = nwe.to_crs(epsg=TARGET_SRID)
    if "Range" not in nwe.columns:
        raise ValueError("Nuwara Eliya LHMP is missing its Range class field")

    raw_class = pd.to_numeric(nwe["Range"], errors="raise")
    nwe_zones = gpd.GeoDataFrame(
        {
            "zone_id": [
                "NWE-NBRI-{:05d}".format(index + 1)
                for index in range(len(nwe))
            ],
            "district": "Nuwara Eliya",
            "hazard_class": raw_class,
            "hazard_label": raw_class.map({
                1: "Landslides not likely to occur (Low)",
                2: "Modest level of landslide hazard",
                3: "Landslides are to be expected (High)",
                4: "Very high / extreme risk",
            }).fillna("Unmapped source LHMP class"),
            "source_hazard_class": raw_class,
            "centroid_lat": None,
            "centroid_lon": None,
            "geometry_crs": "EPSG:5234",
            "source_type": "official",
            "is_synthetic": False,
            "accepted_for_prototype": True,
        },
        geometry=nwe.geometry,
        crs=nwe.crs,
    )
    centroids = nwe_zones.geometry.centroid.to_crs(epsg=4326)
    nwe_zones["centroid_lat"] = centroids.y
    nwe_zones["centroid_lon"] = centroids.x

    for frame in (synthetic_zones, nwe_zones):
        if "source_hazard_class" not in frame:
            frame["source_hazard_class"] = frame["hazard_class"]
    columns = list(dict.fromkeys(
        list(synthetic_zones.columns) + list(nwe_zones.columns)
    ))
    merged = pd.concat(
        [synthetic_zones.reindex(columns=columns), nwe_zones.reindex(columns=columns)],
        ignore_index=True,
    )
    return gpd.GeoDataFrame(
        merged,
        geometry="geometry",
        crs="EPSG:{}".format(TARGET_SRID),
    )


def _read_graph_layers(graph_gpkg=GRAPH_GPKG):
    layers = {}
    for layer in ("road_edges", "road_nodes", "district_boundaries"):
        frame = gpd.read_file(graph_gpkg, layer=layer)
        if frame.crs is None or frame.crs.to_epsg() != TARGET_SRID:
            raise ValueError(
                "{} must be projected to EPSG:{}".format(layer, TARGET_SRID)
            )
        layers[layer] = frame
    return layers


def prepare_tables(input_dir=INPUT_DIR, graph_gpkg=GRAPH_GPKG):
    _check_inputs(input_dir, graph_gpkg)
    tables = _read_graph_layers(graph_gpkg)

    for dataset in DATASET_TABLES:
        if dataset == "lhmp_zones":
            tables[dataset] = _read_lhmp_zones(input_dir)
        elif dataset in WKT_TABLES:
            tables[dataset] = _read_wkt_layer(dataset, input_dir)
        elif dataset in POINT_TABLES:
            tables[dataset] = _read_point_layer(dataset, input_dir)
        else:
            tables[dataset] = _read_csv(dataset, input_dir)

    tables["rda_crosswalk"] = pd.read_csv(
        ROAD_GRAPH_DIR / "rda_crosswalk.csv"
    )
    for table_name, frame in tables.items():
        if frame.empty:
            raise ValueError("Refusing to load an empty table: {}".format(table_name))
    return tables


def _quoted(identifier):
    if not identifier.replace("_", "").isalnum():
        raise ValueError("Unsafe SQL identifier: {}".format(identifier))
    return '"{}"'.format(identifier)


def _load_table(engine, schema, table_name, frame):
    if isinstance(frame, gpd.GeoDataFrame):
        frame.to_postgis(
            table_name,
            engine,
            schema=schema,
            if_exists="fail",
            index=False,
            chunksize=5000,
        )
    else:
        frame.to_sql(
            table_name,
            engine,
            schema=schema,
            if_exists="fail",
            index=False,
            chunksize=1000,
            method="multi",
        )


def _add_constraints_and_indexes(engine, schema, tables):
    from sqlalchemy import text

    schema_q = _quoted(schema)
    for table_name, columns in PRIMARY_KEYS.items():
        table_q = _quoted(table_name)
        column_list = ", ".join(_quoted(column) for column in columns)
        constraint_q = _quoted("{}_pkey".format(table_name))
        with engine.begin() as connection:
            connection.execute(text(
                "ALTER TABLE {}.{} ADD CONSTRAINT {} PRIMARY KEY ({})".format(
                    schema_q, table_q, constraint_q, column_list
                )
            ))

    indexes = {
        "road_edges": [("rda_code", "rda_code_idx"), ("ref", "osm_ref_idx")],
        "hazard_polygons": [("scenario_id", "scenario_idx"), ("event_id", "event_idx")],
        "road_closures": [("event_id", "event_idx"), ("status", "status_idx")],
        "evacuation_origins": [("scenario_id", "scenario_idx"), ("district", "district_idx")],
        "shelters": [("district", "district_idx"), ("operational_status", "status_idx")],
    }
    for table_name, column_indexes in indexes.items():
        for column_name, suffix in column_indexes:
            index_name = _quoted("{}_{}".format(table_name, suffix))
            with engine.begin() as connection:
                connection.execute(text(
                    "CREATE INDEX {} ON {}.{} ({})".format(
                        index_name,
                        schema_q,
                        _quoted(table_name),
                        _quoted(column_name),
                    )
                ))


def _table_counts(engine, schema, tables):
    from sqlalchemy import text

    counts = {}
    for table_name in tables:
        with engine.connect() as connection:
            counts[table_name] = connection.execute(
                text("SELECT count(*) FROM {}.{}".format(
                    _quoted(schema), _quoted(table_name)
                ))
            ).scalar_one()
    return counts


def _geometry_srids(engine, schema, tables):
    from sqlalchemy import text

    srids = {}
    for table_name, frame in tables.items():
        if not isinstance(frame, gpd.GeoDataFrame):
            continue
        with engine.connect() as connection:
            srids[table_name] = connection.execute(text(
                "SELECT DISTINCT ST_SRID(geometry) FROM {}.{}".format(
                    _quoted(schema), _quoted(table_name)
                )
            )).scalars().all()
    return srids


def _verify_indexes(engine, schema, tables):
    from sqlalchemy import text

    with engine.connect() as connection:
        primary_keys = set(connection.execute(text(
            "SELECT relation.relname FROM pg_constraint AS constraint_row "
            "JOIN pg_class AS relation ON relation.oid = constraint_row.conrelid "
            "JOIN pg_namespace AS namespace ON namespace.oid = relation.relnamespace "
            "WHERE namespace.nspname = :schema AND constraint_row.contype = 'p'"
        ), {"schema": schema}).scalars().all())
        expected_primary_keys = set(PRIMARY_KEYS)
        if primary_keys != expected_primary_keys:
            raise ValueError(
                "PostGIS primary-key verification failed: expected {}, got {}".format(
                    sorted(expected_primary_keys), sorted(primary_keys)
                )
            )

        gist_indexes = {}
        for table_name, frame in tables.items():
            if not isinstance(frame, gpd.GeoDataFrame):
                continue
            count = connection.execute(text(
                "SELECT count(*) FROM pg_indexes "
                "WHERE schemaname = :schema AND tablename = :table "
                "AND indexdef ILIKE '%USING gist%'"
            ), {"schema": schema, "table": table_name}).scalar_one()
            if count < 1:
                raise ValueError(
                    "PostGIS spatial index is missing for {}".format(table_name)
                )
            gist_indexes[table_name] = int(count)
    return gist_indexes


def load_to_postgis(tables, engine, replace=False, output_dir=INPUT_DIR):
    from sqlalchemy import text

    stage_schema = "route_stage_{}".format(uuid.uuid4().hex[:12])
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
        connection.execute(text("CREATE SCHEMA {}".format(_quoted(stage_schema))))
        postgis_version = connection.execute(
            text("SELECT PostGIS_Full_Version()")
        ).scalar_one()

    try:
        for table_name, frame in tables.items():
            _load_table(engine, stage_schema, table_name, frame)
        _add_constraints_and_indexes(engine, stage_schema, tables)
        counts = _table_counts(engine, stage_schema, tables)
        srids = _geometry_srids(engine, stage_schema, tables)
        gist_indexes = _verify_indexes(engine, stage_schema, tables)
        expected = {name: int(len(frame)) for name, frame in tables.items()}
        if counts != expected:
            raise ValueError(
                "PostGIS row counts do not match input rows: expected {}, got {}".format(
                    expected, counts
                )
            )
        incorrect_srids = {
            name: values for name, values in srids.items()
            if values != [TARGET_SRID]
        }
        if incorrect_srids:
            raise ValueError(
                "Spatial tables have unexpected SRIDs: {}".format(incorrect_srids)
            )

        with engine.begin() as connection:
            exists = connection.execute(text(
                "SELECT EXISTS (SELECT 1 FROM information_schema.schemata "
                "WHERE schema_name = :schema)"
            ), {"schema": TARGET_SCHEMA}).scalar_one()
            if exists and not replace:
                raise FileExistsError(
                    "Schema {} already exists; use --replace to replace it".format(
                        TARGET_SCHEMA
                    )
                )
            if exists:
                connection.execute(text(
                    "DROP SCHEMA {} CASCADE".format(_quoted(TARGET_SCHEMA))
                ))
            connection.execute(text(
                "ALTER SCHEMA {} RENAME TO {}".format(
                    _quoted(stage_schema), _quoted(TARGET_SCHEMA)
                )
            ))
    except Exception:
        with engine.begin() as connection:
            connection.execute(text(
                "DROP SCHEMA IF EXISTS {} CASCADE".format(_quoted(stage_schema))
            ))
        raise

    output_dir = Path(output_dir)
    report = {
        "loaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": os.getenv("ROUTING_DB_NAME", DATABASE),
        "host": os.getenv("ROUTING_DB_HOST", DATABASE_HOST),
        "port": int(os.getenv("ROUTING_DB_PORT", DATABASE_PORT)),
        "schema": TARGET_SCHEMA,
        "postgis_full_version": postgis_version,
        "target_srid": TARGET_SRID,
        "row_counts": counts,
        "geometry_srids": srids,
        "primary_keys": sorted(PRIMARY_KEYS),
        "gist_indexes": gist_indexes,
        "replace_existing_schema": bool(replace),
    }
    report_path = output_dir / "postgis_load_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report, report_path


def main():
    parser = argparse.ArgumentParser(
        description="Load the prepared dual-route inputs into local PostGIS."
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace the existing dual_route schema after a successful staging load.",
    )
    args = parser.parse_args()
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        tables = prepare_tables()
        report, report_path = load_to_postgis(
            tables,
            engine,
            replace=args.replace,
        )
    except (FileNotFoundError, FileExistsError, ValueError, OSError, ImportError) as exc:
        print("PostGIS input load failed: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print(
        "Loaded {} tables into {}.{} on {}:{}".format(
            len(report["row_counts"]),
            report["database"],
            report["schema"],
            report["host"],
            report["port"],
        )
    )
    for table, count in report["row_counts"].items():
        print("  {}: {}".format(table, count))
    print("PostGIS: {}".format(report["postgis_full_version"]))
    print("Load report: {}".format(report_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
