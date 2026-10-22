import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import sys
import uuid

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import URL


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "processed_data" / "dual_route"
SCHEMA = "dual_route"
DATABASE = "dual_route"
DATABASE_USER = "dual_route"
DATABASE_HOST = "127.0.0.1"
DATABASE_PORT = 55432
INCIDENT_SNAP_BUFFER_METERS = 50
CLOSURE_NEAREST_REVIEW_METERS = 50
TARGET_SRID = 5234
OUTPUT_TABLES = (
    "edge_hazard_matches",
    "edge_closure_matches",
    "closure_nearest_edge",
    "edge_lhmp_matches",
    "incident_edge_matches",
    "edge_static_risk",
)
OUTPUT_VIEW = "edge_scenario_status"


def database_url():
    return URL.create(
        "postgresql+psycopg2",
        username=os.getenv("ROUTING_DB_USER", DATABASE_USER),
        password=os.getenv("ROUTING_DB_PASSWORD"),
        host=os.getenv("ROUTING_DB_HOST", DATABASE_HOST),
        port=int(os.getenv("ROUTING_DB_PORT", DATABASE_PORT)),
        database=os.getenv("ROUTING_DB_NAME", DATABASE),
    )


def _identifier(value):
    if not re.fullmatch(r"[a-z][a-z0-9_]*", value):
        raise ValueError("Unsafe SQL identifier: {}".format(value))
    return '"{}"'.format(value)


def _create_overlay_tables(connection, stage_schema):
    stage = _identifier(stage_schema)
    connection.execute(text("""
        CREATE TABLE {schema}.edge_hazard_matches AS
        SELECT
            edge.edge_id,
            hazard.hazard_id,
            hazard.event_id,
            hazard.scenario_id,
            hazard.district,
            lower(hazard.hazard_type::text) AS hazard_type,
            hazard.severity,
            hazard.water_depth_m,
            hazard.valid_from,
            hazard.valid_to,
            hazard.source_type,
            hazard.is_synthetic,
            hazard.accepted_for_prototype
        FROM dual_route.road_edges AS edge
        JOIN dual_route.hazard_polygons AS hazard
          ON ST_Intersects(edge.geometry, hazard.geometry)
        WHERE lower(hazard.hazard_type::text) IN ('flood', 'landslide')
    """.format(schema=stage)))

    connection.execute(text("""
        CREATE TABLE {schema}.edge_closure_matches AS
        SELECT
            edge.edge_id,
            closure.closure_id,
            closure.event_id,
            event.scenario_id,
            closure.district,
            lower(closure.closure_type::text) AS closure_type,
            lower(closure.status::text) AS status,
            closure.road_ref,
            closure.road_name,
            closure.osm_way_id,
            closure.valid_from,
            closure.valid_to,
            closure.reason,
            closure.source_type,
            closure.is_synthetic,
            closure.accepted_for_prototype
        FROM dual_route.road_edges AS edge
        JOIN dual_route.road_closures AS closure
          ON ST_Intersects(edge.geometry, closure.geometry)
        JOIN dual_route.events AS event
          ON event.event_id = closure.event_id
    """.format(schema=stage)))

    connection.execute(text("""
        CREATE TABLE {schema}.closure_nearest_edge AS
        SELECT
            closure.closure_id,
            closure.event_id,
            event.scenario_id,
            closure.district,
            lower(closure.closure_type::text) AS closure_type,
            lower(closure.status::text) AS status,
            nearest.edge_id AS nearest_edge_id,
            nearest.distance_m,
            (nearest.distance_m <= :buffer_meters) AS within_50m,
            exists (
                SELECT 1
                FROM {schema}.edge_closure_matches AS direct_match
                WHERE direct_match.closure_id = closure.closure_id
            ) AS intersects_edge,
            closure.source_type,
            closure.is_synthetic,
            closure.accepted_for_prototype
        FROM dual_route.road_closures AS closure
        JOIN dual_route.events AS event USING (event_id)
        CROSS JOIN LATERAL (
            SELECT
                edge.edge_id,
                ST_Distance(edge.geometry, closure.geometry) AS distance_m
            FROM dual_route.road_edges AS edge
            ORDER BY edge.geometry <-> closure.geometry, edge.edge_id
            LIMIT 1
        ) AS nearest
    """.format(schema=stage)), {
        "buffer_meters": CLOSURE_NEAREST_REVIEW_METERS
    })

    connection.execute(text("""
        CREATE TABLE {schema}.edge_lhmp_matches AS
        SELECT
            edge.edge_id,
            zone.zone_id,
            zone.district,
            zone.hazard_class,
            zone.source_hazard_class,
            zone.hazard_label,
            zone.source_type,
            zone.is_synthetic,
            zone.accepted_for_prototype,
            (zone.hazard_class IN (3, 4)) AS soft_penalty_eligible
        FROM dual_route.road_edges AS edge
        JOIN dual_route.lhmp_zones AS zone
          ON ST_Intersects(edge.geometry, zone.geometry)
    """.format(schema=stage)))

    connection.execute(text("""
        CREATE TABLE {schema}.incident_edge_matches AS
        SELECT
            incident.incident_record_id,
            incident.incident_id,
            incident.event_id,
            incident.district,
            incident.incident_type,
            incident.occurred_at,
            incident.severity,
            nearest.edge_id,
            nearest.distance_m,
            (nearest.distance_m <= :buffer_meters) AS within_50m,
            incident.source_type,
            incident.is_synthetic,
            incident.accepted_for_prototype
        FROM dual_route.incident_points AS incident
        CROSS JOIN LATERAL (
            SELECT
                edge.edge_id,
                ST_Distance(edge.geometry, incident.geometry) AS distance_m
            FROM dual_route.road_edges AS edge
            ORDER BY edge.geometry <-> incident.geometry, edge.edge_id
            LIMIT 1
        ) AS nearest
    """.format(schema=stage)), {"buffer_meters": INCIDENT_SNAP_BUFFER_METERS})

    connection.execute(text("""
        CREATE TABLE {schema}.edge_static_risk AS
        WITH high_lhmp AS (
            SELECT
                edge_id,
                count(*)::integer AS high_lhmp_zone_count,
                max(hazard_class)::integer AS max_lhmp_class
            FROM {schema}.edge_lhmp_matches
            WHERE soft_penalty_eligible
            GROUP BY edge_id
        ),
        incident_density AS (
            SELECT
                edge_id,
                count(*) FILTER (WHERE within_50m)::integer AS incident_count_50m,
                min(distance_m) FILTER (WHERE within_50m) AS nearest_incident_distance_m,
                count(*)::integer AS incident_count_snapped
            FROM {schema}.incident_edge_matches
            GROUP BY edge_id
        )
        SELECT
            edge.edge_id,
            coalesce(high_lhmp.high_lhmp_zone_count, 0)::integer
                AS high_lhmp_zone_count,
            high_lhmp.max_lhmp_class,
            coalesce(incident_density.incident_count_50m, 0)::integer
                AS incident_count_50m,
            coalesce(incident_density.incident_count_snapped, 0)::integer
                AS incident_count_snapped,
            incident_density.nearest_incident_distance_m,
            CASE
                WHEN edge.length > 0
                THEN coalesce(incident_density.incident_count_50m, 0)
                    / (edge.length / 1000.0)
                ELSE 0.0
            END AS incident_density_per_km,
            (
                coalesce(high_lhmp.high_lhmp_zone_count, 0) > 0
                OR coalesce(incident_density.incident_count_50m, 0) > 0
            ) AS soft_penalty_eligible
        FROM dual_route.road_edges AS edge
        LEFT JOIN high_lhmp USING (edge_id)
        LEFT JOIN incident_density USING (edge_id)
    """.format(schema=stage)))


def _create_indexes(connection, stage_schema):
    stage = _identifier(stage_schema)
    indexes = (
        ("edge_hazard_matches", "edge_id"),
        ("edge_hazard_matches", "scenario_id"),
        ("edge_closure_matches", "edge_id"),
        ("edge_closure_matches", "scenario_id"),
        ("closure_nearest_edge", "nearest_edge_id"),
        ("closure_nearest_edge", "within_50m"),
        ("edge_lhmp_matches", "edge_id"),
        ("edge_lhmp_matches", "zone_id"),
        ("incident_edge_matches", "edge_id"),
        ("incident_edge_matches", "within_50m"),
        ("edge_static_risk", "edge_id"),
    )
    for table, column in indexes:
        connection.execute(text(
            "CREATE INDEX {index} ON {schema}.{table} ({column})".format(
                index=_identifier("{}_{}_idx".format(table, column)),
                schema=stage,
                table=_identifier(table),
                column=_identifier(column),
            )
        ))

    primary_keys = (
        ("edge_hazard_matches", ("edge_id", "hazard_id")),
        ("edge_closure_matches", ("edge_id", "closure_id")),
        ("closure_nearest_edge", ("closure_id",)),
        ("edge_lhmp_matches", ("edge_id", "zone_id")),
        ("incident_edge_matches", ("incident_record_id",)),
        ("edge_static_risk", ("edge_id",)),
    )
    for table, columns in primary_keys:
        connection.execute(text(
            "ALTER TABLE {schema}.{table} ADD CONSTRAINT {constraint} "
            "PRIMARY KEY ({columns})".format(
                schema=stage,
                table=_identifier(table),
                constraint=_identifier("{}_pkey".format(table)),
                columns=", ".join(_identifier(column) for column in columns),
            )
        ))

def _create_status_view(connection, stage_schema):
    stage = _identifier(stage_schema)
    connection.execute(text("""
        CREATE VIEW {schema}.edge_scenario_status AS
        WITH scenario_hazards AS (
            SELECT
                hit.edge_id,
                hit.scenario_id,
                count(*) FILTER (
                    WHERE hit.hazard_type IN ('flood', 'landslide')
                )::integer AS hard_hazard_count,
                count(*) FILTER (
                    WHERE hit.hazard_type = 'flood'
                )::integer AS flood_match_count,
                count(*) FILTER (
                    WHERE hit.hazard_type = 'landslide'
                )::integer AS landslide_match_count
            FROM {schema}.edge_hazard_matches AS hit
            JOIN dual_route.events AS event
              ON event.scenario_id = hit.scenario_id
             AND event.event_id = hit.event_id
            WHERE hit.valid_from <= event.ended_at
              AND hit.valid_to >= event.started_at
            GROUP BY hit.edge_id, hit.scenario_id
        ),
        scenario_closures AS (
            SELECT
                    hit.edge_id,
                    hit.scenario_id,
                count(*) FILTER (
                        WHERE hit.status = 'closed'
                )::integer AS closed_closure_count,
                count(*) FILTER (
                        WHERE hit.status = 'restricted'
                )::integer AS restricted_closure_count,
                count(*) FILTER (
                        WHERE hit.status = 'reopened'
                )::integer AS reopened_closure_count
                FROM {schema}.edge_closure_matches AS hit
            JOIN dual_route.events AS event
                  ON event.scenario_id = hit.scenario_id
                 AND event.event_id = hit.event_id
                WHERE hit.valid_from <= event.ended_at
                  AND hit.valid_to >= event.started_at
                GROUP BY hit.edge_id, hit.scenario_id
        ),
        scenario_edges AS (
            SELECT
                event.event_id,
                event.scenario_id,
                event.hazard_type AS scenario_hazard_type,
                event.district AS scenario_district,
                event.started_at AS scenario_started_at,
                event.ended_at AS scenario_ended_at,
                edge.edge_id,
                edge.length AS edge_length_m,
                edge.travel_time,
                edge.rda_code,
                edge.rda_class,
                edge.rda_subclass,
                coalesce(hazard.hard_hazard_count, 0)::integer
                    AS hard_hazard_count,
                coalesce(hazard.flood_match_count, 0)::integer
                    AS flood_match_count,
                coalesce(hazard.landslide_match_count, 0)::integer
                    AS landslide_match_count,
                coalesce(closure.closed_closure_count, 0)::integer
                    AS closed_closure_count,
                coalesce(closure.restricted_closure_count, 0)::integer
                    AS restricted_closure_count,
                coalesce(closure.reopened_closure_count, 0)::integer
                    AS reopened_closure_count,
                risk.high_lhmp_zone_count,
                risk.max_lhmp_class,
                risk.incident_count_50m,
                risk.incident_count_snapped,
                risk.nearest_incident_distance_m,
                risk.incident_density_per_km,
                risk.soft_penalty_eligible AS hazard_soft_penalty_eligible,
                (
                    coalesce(hazard.hard_hazard_count, 0) > 0
                    OR coalesce(closure.closed_closure_count, 0) > 0
                ) AS hard_blocked
            FROM dual_route.events AS event
            CROSS JOIN dual_route.road_edges AS edge
            JOIN {schema}.edge_static_risk AS risk USING (edge_id)
            LEFT JOIN scenario_hazards AS hazard
              ON hazard.edge_id = edge.edge_id
             AND hazard.scenario_id = event.scenario_id
            LEFT JOIN scenario_closures AS closure
              ON closure.edge_id = edge.edge_id
             AND closure.scenario_id = event.scenario_id
        )
        SELECT
            *,
            (
                hazard_soft_penalty_eligible
                OR restricted_closure_count > 0
            ) AS soft_penalty_eligible,
            CASE
                WHEN hard_blocked THEN 'hard_blocked'
                WHEN hazard_soft_penalty_eligible
                     OR restricted_closure_count > 0 THEN 'soft_penalty'
                ELSE 'open'
            END AS hazard_tier,
            CASE
                WHEN hard_hazard_count > 0 AND closed_closure_count > 0
                    THEN 'flood_or_landslide_and_closed_closure'
                WHEN hard_hazard_count > 0 THEN 'flood_or_landslide'
                WHEN closed_closure_count > 0 THEN 'closed_closure'
                ELSE NULL
            END AS hard_block_reason,
            'any matching evidence during the scenario event window'
                AS status_time_basis
        FROM scenario_edges
    """.format(schema=stage)))


def _scalar(connection, statement, parameters=None):
    return connection.execute(text(statement), parameters or {}).scalar_one()


def _validate_staged_outputs(connection, stage_schema):
    stage = _identifier(stage_schema)
    input_incident_count = _scalar(
        connection,
        "SELECT count(*) FROM dual_route.incident_points",
    )
    matched_incident_count = _scalar(
        connection,
        "SELECT count(*) FROM {}.incident_edge_matches".format(stage),
    )
    if input_incident_count != matched_incident_count:
        raise ValueError(
            "Not all incidents were snapped to an edge: {}/{}".format(
                matched_incident_count, input_incident_count
            )
        )

    incorrect_srid_count = _scalar(connection, """
        SELECT count(*)
        FROM geometry_columns
        WHERE f_table_schema = :schema
          AND f_table_name IN ('road_edges', 'hazard_polygons', 'road_closures',
                               'lhmp_zones', 'incident_points')
          AND srid <> :srid
    """, {"schema": SCHEMA, "srid": TARGET_SRID})
    if incorrect_srid_count:
        raise ValueError(
            "{} source spatial tables have an unexpected SRID".format(
                incorrect_srid_count
            )
        )

    scenario_count = _scalar(
        connection,
        "SELECT count(*) FROM dual_route.events",
    )
    edge_count = _scalar(
        connection,
        "SELECT count(*) FROM dual_route.road_edges",
    )
    status_count = _scalar(
        connection,
        "SELECT count(*) FROM {}.edge_scenario_status".format(stage),
    )
    expected_status_count = scenario_count * edge_count
    if status_count != expected_status_count:
        raise ValueError(
        "Scenario view has {} rows; expected {} edges x {} scenarios = {}".format(
            status_count, edge_count, scenario_count, expected_status_count
        )
        )
    invalid_tier_count = _scalar(connection, """
        SELECT count(*)
        FROM {schema}.edge_scenario_status
        WHERE hard_blocked <> (
            hard_hazard_count > 0 OR closed_closure_count > 0
        )
           OR hazard_tier <> CASE
                WHEN hard_blocked THEN 'hard_blocked'
                WHEN hazard_soft_penalty_eligible
                     OR restricted_closure_count > 0 THEN 'soft_penalty'
                ELSE 'open'
              END
    """.format(schema=stage))
    if invalid_tier_count:
        raise ValueError(
            "{} scenario edge rows have an inconsistent hazard tier".format(
                invalid_tier_count
            )
        )

    closures_matched = _scalar(
        connection,
        "SELECT count(DISTINCT closure_id) FROM {}.edge_closure_matches".format(stage),
    )
    closures_within_tolerance = _scalar(connection, """
        SELECT count(*)
        FROM {schema}.closure_nearest_edge
        WHERE NOT intersects_edge AND within_50m
    """.format(schema=stage))
    closures_over_tolerance = _scalar(connection, """
        SELECT count(*)
        FROM {schema}.closure_nearest_edge
        WHERE NOT intersects_edge AND NOT within_50m
    """.format(schema=stage))
    total_closures = _scalar(
        connection,
        "SELECT count(*) FROM dual_route.road_closures",
    )

    return {
        "edge_hazard_matches": _scalar(
            connection,
            "SELECT count(*) FROM {}.edge_hazard_matches".format(stage),
        ),
        "edge_closure_matches": _scalar(
            connection,
            "SELECT count(*) FROM {}.edge_closure_matches".format(stage),
        ),
        "source_closures": total_closures,
        "closures_with_intersecting_edges": closures_matched,
        "unmatched_closures_with_nearest_edge_within_50m": closures_within_tolerance,
        "unmatched_closures_over_50m_from_nearest_edge": closures_over_tolerance,
        "closure_nearest_edge_candidates": _scalar(
            connection,
            "SELECT count(*) FROM {}.closure_nearest_edge".format(stage),
        ),
        "edge_lhmp_matches": _scalar(
            connection,
            "SELECT count(*) FROM {}.edge_lhmp_matches".format(stage),
        ),
        "incident_edge_matches": matched_incident_count,
        "incidents_within_50m": _scalar(
            connection,
            "SELECT count(*) FROM {}.incident_edge_matches WHERE within_50m".format(stage),
        ),
        "incidents_over_50m": _scalar(
            connection,
            "SELECT count(*) FROM {}.incident_edge_matches WHERE NOT within_50m".format(stage),
        ),
        "edge_static_risk": _scalar(
            connection,
            "SELECT count(*) FROM {}.edge_static_risk".format(stage),
        ),
        "scenario_status_rows": status_count,
        "expected_scenario_status_rows": expected_status_count,
        "invalid_scenario_tier_rows": invalid_tier_count,
    }


def _scenario_summary(connection, schema_name, view_name):
    view = "{}.{}".format(
        _identifier(schema_name),
        _identifier(view_name),
    )
    rows = connection.execute(text(
        "SELECT scenario_id, scenario_district, scenario_hazard_type, "
        "count(*) FILTER (WHERE hazard_tier = 'hard_blocked') AS hard_blocked_edges, "
        "count(*) FILTER (WHERE hazard_tier = 'soft_penalty') AS soft_penalty_edges, "
        "count(*) FILTER (WHERE hazard_tier = 'open') AS open_edges "
        "FROM {} GROUP BY scenario_id, scenario_district, scenario_hazard_type "
        "ORDER BY scenario_id".format(view)
    )).mappings().all()
    return [dict(row) for row in rows]


def _scenario_input_coverage(connection):
    rows = connection.execute(text("""
        SELECT
            event.scenario_id,
            event.event_id,
            event.district,
            event.hazard_type,
            coalesce(hazards.polygon_count, 0) AS hazard_polygon_count,
            coalesce(incidents.incident_count, 0) AS linked_incident_count,
            coalesce(closures.closure_count, 0) AS closure_count,
            coalesce(origins.origin_count, 0) AS evacuation_origin_count
        FROM dual_route.events AS event
        LEFT JOIN (
            SELECT event_id, count(*) AS polygon_count
            FROM dual_route.hazard_polygons
            GROUP BY event_id
        ) AS hazards USING (event_id)
        LEFT JOIN (
            SELECT event_id, count(*) AS incident_count
            FROM dual_route.incident_points
            GROUP BY event_id
        ) AS incidents USING (event_id)
        LEFT JOIN (
            SELECT event_id, count(*) AS closure_count
            FROM dual_route.road_closures
            GROUP BY event_id
        ) AS closures USING (event_id)
        LEFT JOIN (
            SELECT scenario_id, count(*) AS origin_count
            FROM dual_route.evacuation_origins
            GROUP BY scenario_id
        ) AS origins USING (scenario_id)
        ORDER BY event.scenario_id
    """)).mappings().all()
    return [dict(row) for row in rows]


def _hazard_source_coverage(connection, stage_schema):
    stage = _identifier(stage_schema)
    rows = connection.execute(text("""
        SELECT
            hazard.hazard_type,
            count(DISTINCT hazard.hazard_id) AS source_polygon_count,
            count(DISTINCT hit.hazard_id) AS polygons_intersecting_roads
        FROM dual_route.hazard_polygons AS hazard
        LEFT JOIN {schema}.edge_hazard_matches AS hit
          ON hit.hazard_id = hazard.hazard_id
        GROUP BY hazard.hazard_type
        ORDER BY hazard.hazard_type
    """.format(schema=stage))).mappings().all()
    return [dict(row) for row in rows]


def _publish_outputs(engine, stage_schema, replace):
    stage = _identifier(stage_schema)
    schema = _identifier(SCHEMA)
    with engine.begin() as connection:
        existing = connection.execute(text(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = :schema AND table_name IN :tables"
        ).bindparams(bindparam("tables", expanding=True)), {
            "schema": SCHEMA,
            "tables": OUTPUT_TABLES,
        }).scalars().all()
        existing_view = _scalar(connection, """
            SELECT EXISTS (
                SELECT 1 FROM information_schema.views
                WHERE table_schema = :schema AND table_name = :view
            )
        """, {"schema": SCHEMA, "view": OUTPUT_VIEW})
        if (existing or existing_view) and not replace:
            raise FileExistsError(
                "Overlay outputs already exist; use --replace to rebuild them"
            )
        if existing_view:
            connection.execute(text(
                "DROP VIEW {}.{}".format(schema, _identifier(OUTPUT_VIEW))
            ))
        for table_name in OUTPUT_TABLES:
            if table_name in existing:
                connection.execute(text(
                    "DROP TABLE {}.{}".format(schema, _identifier(table_name))
                ))
        for table_name in OUTPUT_TABLES:
            connection.execute(text(
                "ALTER TABLE {}.{} SET SCHEMA {}".format(
                    stage, _identifier(table_name), schema
                )
            ))
        connection.execute(text(
            "ALTER VIEW {}.{} SET SCHEMA {}".format(
                stage, _identifier(OUTPUT_VIEW), schema
            )
        ))
        connection.execute(text(
            "DROP SCHEMA {}".format(stage)
        ))


def build_edge_hazard_status(engine, replace=False, output_dir=OUTPUT_DIR):
    stage_schema = "overlay_stage_{}".format(uuid.uuid4().hex[:12])
    with engine.begin() as connection:
        schema_exists = _scalar(
            connection,
            "SELECT EXISTS (SELECT 1 FROM information_schema.schemata "
            "WHERE schema_name = :schema)",
            {"schema": SCHEMA},
        )
        if not schema_exists:
            raise ValueError(
                "Required PostGIS schema {!r} does not exist".format(SCHEMA)
            )
        missing_tables = connection.execute(text("""
            SELECT required.table_name
            FROM (VALUES
                ('road_edges'), ('hazard_polygons'), ('road_closures'),
                ('events'), ('lhmp_zones'), ('incident_points')
            ) AS required(table_name)
            WHERE NOT EXISTS (
                SELECT 1 FROM information_schema.tables AS present
                WHERE present.table_schema = :schema
                  AND present.table_name = required.table_name
            )
            ORDER BY required.table_name
        """), {"schema": SCHEMA}).scalars().all()
        if missing_tables:
            raise ValueError(
                "Missing Task 1 PostGIS tables: {}".format(", ".join(missing_tables))
            )
        orphan_closures = _scalar(connection, """
            SELECT count(*)
            FROM dual_route.road_closures AS closure
            LEFT JOIN dual_route.events AS event USING (event_id)
            WHERE event.event_id IS NULL OR event.scenario_id IS NULL
        """)
        if orphan_closures:
            raise ValueError(
                "{} closure rows cannot be assigned to a scenario".format(
                    orphan_closures
                )
            )
        connection.execute(text("CREATE SCHEMA {}".format(_identifier(stage_schema))))

    try:
        with engine.begin() as connection:
            _create_overlay_tables(connection, stage_schema)
            _create_indexes(connection, stage_schema)
            _create_status_view(connection, stage_schema)
            for table_name in OUTPUT_TABLES:
                connection.execute(text(
                    "ANALYZE {}.{}".format(
                        _identifier(stage_schema), _identifier(table_name)
                    )
                ))
            match_counts = _validate_staged_outputs(connection, stage_schema)
            scenario_status_counts = _scenario_summary(
                connection,
                stage_schema,
                OUTPUT_VIEW,
            )
            scenario_input_coverage = _scenario_input_coverage(connection)
            hazard_source_coverage = _hazard_source_coverage(
                connection,
                stage_schema,
            )
        _publish_outputs(engine, stage_schema, replace)
    finally:
        with engine.begin() as connection:
            connection.execute(text(
                "DROP SCHEMA IF EXISTS {} CASCADE".format(
                    _identifier(stage_schema)
                )
            ))

    report = {
        "built_at_utc": datetime.now(timezone.utc).isoformat(),
        "database": os.getenv("ROUTING_DB_NAME", DATABASE),
        "host": os.getenv("ROUTING_DB_HOST", DATABASE_HOST),
        "port": int(os.getenv("ROUTING_DB_PORT", DATABASE_PORT)),
        "schema": SCHEMA,
        "target_srid": TARGET_SRID,
        "incident_snap_buffer_meters": INCIDENT_SNAP_BUFFER_METERS,
        "closure_nearest_candidate_review_meters": CLOSURE_NEAREST_REVIEW_METERS,
        "hard_block_policy": (
            "Flood/landslide intersections and closed road/bridge closures; "
            "closure and hazard evidence must overlap the scenario event window."
        ),
        "soft_penalty_policy": (
            "LHMP classes 3-4 and incident points snapped to their nearest edge "
            "within 50m. Active restricted closures are separately exposed and "
            "also receive the soft_penalty tier."
        ),
        "status_time_basis": (
            "Scenario status is conservative over any part of each scenario's "
            "event window, not an as-of-time closure query."
        ),
        "match_counts": match_counts,
        "hazard_source_coverage": hazard_source_coverage,
        "scenario_input_coverage": scenario_input_coverage,
        "scenario_status_counts": scenario_status_counts,
        "outputs": {
            "tables": list(OUTPUT_TABLES),
            "view": OUTPUT_VIEW,
            "open_edge_representation": (
                "Every edge/scenario pair appears in edge_scenario_status; "
                "open rows are explicit."
            ),
            "closure_nearest_candidates": (
                "Nearest-edge candidates are diagnostic only. They do not create "
                "closure matches or blocks unless the closure geometry intersects "
                "the edge."
            ),
        },
    }
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "edge_hazard_status_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    return report, report_path


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Match hazard, closure, LHMP, and incident evidence to PostGIS road edges."
        )
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Replace previously generated edge overlay outputs.",
    )
    args = parser.parse_args()
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        report, report_path = build_edge_hazard_status(
            engine,
            replace=args.replace,
        )
    except (FileExistsError, ValueError, OSError) as exc:
        print("Edge hazard overlay failed: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    print("Built PostGIS edge overlays in {}.".format(SCHEMA))
    for name, count in report["match_counts"].items():
        print("  {}: {}".format(name, count))
    print("Scenario status rows: {}".format(
        sum(
            row["hard_blocked_edges"]
            + row["soft_penalty_edges"]
            + row["open_edges"]
            for row in report["scenario_status_counts"]
        )
    ))
    print("Report: {}".format(report_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
