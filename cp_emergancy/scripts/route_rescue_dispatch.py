import argparse
import json
import math
import os
from pathlib import Path
import sys

import networkx as nx
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL


PROJECT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_DIR / "processed_data" / "dual_route" / "routes"
DATABASE = "dual_route"
DATABASE_USER = "dual_route"
DATABASE_HOST = "127.0.0.1"
DATABASE_PORT = 55432
SCHEMA = "dual_route"
TARGET_SRID = 5234
MAX_ENDPOINT_SNAP_METERS = 1000.0
INCIDENT_EDGE_BLOCK_CHECK_METERS = 50.0
ENDPOINT_TRANSFORMER = None


def database_url():
    return URL.create(
        "postgresql+psycopg2",
        username=os.getenv("ROUTING_DB_USER", DATABASE_USER),
        password=os.getenv("ROUTING_DB_PASSWORD"),
        host=os.getenv("ROUTING_DB_HOST", DATABASE_HOST),
        port=int(os.getenv("ROUTING_DB_PORT", DATABASE_PORT)),
        database=os.getenv("ROUTING_DB_NAME", DATABASE),
    )


def _build_directed_graph(edge_rows):
    graph = nx.DiGraph()
    for row in edge_rows:
        if row["hard_blocked"]:
            continue
        travel_time = float(row["travel_time"])
        length = float(row["length"])
        if not math.isfinite(travel_time) or travel_time <= 0:
            raise ValueError(
                "Edge {} has invalid travel_time {}".format(
                    row["edge_id"], travel_time
                )
            )
        if not math.isfinite(length) or length < 0:
            raise ValueError(
                "Edge {} has invalid length {}".format(row["edge_id"], length)
            )
        start = int(row["u"])
        end = int(row["v"])
        current = graph.get_edge_data(start, end)
        if current is None or travel_time < current["travel_time"]:
            graph.add_edge(
                start,
                end,
                edge_id=row["edge_id"],
                key=int(row["key"]),
                travel_time=travel_time,
                length=length,
            )
    return graph


def _infeasible(reason, scenario_id, facility, incident, **details):
    result = {
        "status": "infeasible",
        "reason": reason,
        "scenario_id": scenario_id,
        "facility": facility,
        "incident": incident,
        "route": None,
    }
    result.update(details)
    return result


def _compute_shortest_route(graph, source, target):
    if source not in graph:
        return None
    if target not in graph:
        return None
    try:
        nodes = nx.shortest_path(
            graph,
            source=source,
            target=target,
            weight="travel_time",
            method="dijkstra",
        )
    except nx.NetworkXNoPath:
        return None

    edges = []
    total_time = 0.0
    total_length = 0.0
    for start, end in zip(nodes, nodes[1:]):
        edge = graph[start][end]
        total_time += edge["travel_time"]
        total_length += edge["length"]
        edges.append(
            {
                "edge_id": edge["edge_id"],
                "from_node": start,
                "to_node": end,
                "key": edge["key"],
                "travel_time_seconds": edge["travel_time"],
                "length_meters": edge["length"],
            }
        )
    return {
        "node_ids": nodes,
        "edges": edges,
        "edge_ids": [edge["edge_id"] for edge in edges],
        "travel_time_seconds": total_time,
        "distance_meters": total_length,
    }


def _load_dispatch_facility(connection, facility_id):
    row = connection.execute(text("""
        SELECT
            facility.facility_id,
            facility.facility_type,
            facility.district,
            facility.name,
            lower(facility.operational_status::text) AS operational_status,
            facility.source_type,
            facility.is_synthetic,
            ST_X(facility.geometry) AS point_x,
            ST_Y(facility.geometry) AS point_y,
            nearest.node_id,
            nearest.distance_m AS snap_distance_m
        FROM dual_route.dispatch_facilities AS facility
        CROSS JOIN LATERAL (
            SELECT
                node.osmid AS node_id,
                ST_Distance(node.geometry, facility.geometry) AS distance_m
            FROM dual_route.road_nodes AS node
            ORDER BY node.geometry <-> facility.geometry, node.osmid
            LIMIT 1
        ) AS nearest
        WHERE facility.facility_id = :facility_id
    """), {"facility_id": facility_id}).mappings().first()
    if row is None:
        raise ValueError("Unknown dispatch facility_id: {}".format(facility_id))
    return dict(row)


def _load_incident(connection, incident_record_id):
    row = connection.execute(text("""
        SELECT
            incident.incident_record_id,
            incident.incident_id,
            incident.event_id,
            event.scenario_id,
            event.hazard_type AS scenario_hazard_type,
            incident.district,
            incident.incident_type,
            incident.occurred_at,
            incident.severity,
            incident.source_type,
            incident.is_synthetic,
            ST_X(incident.geometry) AS point_x,
            ST_Y(incident.geometry) AS point_y,
            nearest.node_id,
            nearest.distance_m AS snap_distance_m,
            edge_match.edge_id AS nearest_road_edge_id,
            edge_match.distance_m AS nearest_road_edge_distance_m,
            edge_status.hard_blocked AS nearest_road_edge_hard_blocked,
            edge_status.hard_block_reason AS nearest_road_edge_block_reason
        FROM dual_route.incident_points AS incident
        JOIN dual_route.events AS event USING (event_id)
        CROSS JOIN LATERAL (
            SELECT
                node.osmid AS node_id,
                ST_Distance(node.geometry, incident.geometry) AS distance_m
            FROM dual_route.road_nodes AS node
            ORDER BY node.geometry <-> incident.geometry, node.osmid
            LIMIT 1
        ) AS nearest
        LEFT JOIN dual_route.incident_edge_matches AS edge_match
          ON edge_match.incident_record_id = incident.incident_record_id
        LEFT JOIN dual_route.edge_scenario_status AS edge_status
          ON edge_status.scenario_id = event.scenario_id
         AND edge_status.edge_id = edge_match.edge_id
        WHERE incident.incident_record_id = :incident_record_id
    """), {"incident_record_id": incident_record_id}).mappings().first()
    if row is None:
        raise ValueError("Unknown incident_record_id: {}".format(incident_record_id))
    if row["scenario_id"] is None:
        raise ValueError(
            "Incident {} has no linked routing scenario".format(incident_record_id)
        )
    return dict(row)


def _load_scenario_edges(connection, scenario_id):
    rows = connection.execute(text("""
        SELECT
            edge.u,
            edge.v,
            edge.key,
            edge.edge_id,
            edge.travel_time,
            edge.length,
            status.hard_blocked
        FROM dual_route.road_edges AS edge
        JOIN dual_route.edge_scenario_status AS status
          ON status.edge_id = edge.edge_id
         AND status.scenario_id = :scenario_id
        WHERE NOT status.hard_blocked
    """), {"scenario_id": scenario_id}).mappings()
    return list(rows)


def _load_node_coordinates(connection, node_ids):
    rows = connection.execute(text("""
        SELECT osmid, ST_X(geometry) AS x, ST_Y(geometry) AS y
        FROM dual_route.road_nodes
        WHERE osmid = ANY(:node_ids)
    """), {"node_ids": list(node_ids)}).mappings()
    return {int(row["osmid"]): (float(row["x"]), float(row["y"])) for row in rows}


def _route_geometry(connection, facility, incident, route):
    global ENDPOINT_TRANSFORMER
    if ENDPOINT_TRANSFORMER is None:
        from pyproj import Transformer

        ENDPOINT_TRANSFORMER = Transformer.from_crs(
            "EPSG:{}".format(TARGET_SRID),
            "EPSG:4326",
            always_xy=True,
        )
    nodes = _load_node_coordinates(connection, route["node_ids"])
    projected = [(facility["point_x"], facility["point_y"])]
    projected.extend(nodes[node_id] for node_id in route["node_ids"])
    projected.append((incident["point_x"], incident["point_y"]))
    coordinates = [
        list(ENDPOINT_TRANSFORMER.transform(x, y))
        for x, y in projected
    ]
    return {"type": "LineString", "coordinates": coordinates}


def route_rescue_dispatch(engine, facility_id, incident_record_id):
    with engine.connect() as connection:
        facility = _load_dispatch_facility(connection, facility_id)
        incident = _load_incident(connection, incident_record_id)

        scenario_id = incident["scenario_id"]
        facility_result = {
            "facility_id": facility["facility_id"],
            "facility_type": facility["facility_type"],
            "district": facility["district"],
            "name": facility["name"],
            "operational_status": facility["operational_status"],
            "network_snap_distance_m": float(facility["snap_distance_m"]),
        }
        incident_result = {
            "incident_record_id": incident["incident_record_id"],
            "incident_id": incident["incident_id"],
            "event_id": incident["event_id"],
            "district": incident["district"],
            "network_snap_distance_m": float(incident["snap_distance_m"]),
            "nearest_road_edge_id": incident["nearest_road_edge_id"],
            "nearest_road_edge_distance_m": (
                float(incident["nearest_road_edge_distance_m"])
                if incident["nearest_road_edge_distance_m"] is not None
                else None
            ),
        }

        if facility["facility_type"] not in {"DDMC_station", "hospital"}:
            raise ValueError(
                "Facility {} is not a DDMC station or hospital".format(facility_id)
            )
        if facility["operational_status"] not in {"operational", "limited"}:
            return _infeasible(
                "facility_not_available",
                scenario_id,
                facility_result,
                incident_result,
            )
        if facility["snap_distance_m"] > MAX_ENDPOINT_SNAP_METERS:
            return _infeasible(
                "facility_too_far_from_road_network",
                scenario_id,
                facility_result,
                incident_result,
                maximum_snap_distance_m=MAX_ENDPOINT_SNAP_METERS,
            )
        if incident["snap_distance_m"] > MAX_ENDPOINT_SNAP_METERS:
            return _infeasible(
                "incident_too_far_from_road_network",
                scenario_id,
                facility_result,
                incident_result,
                maximum_snap_distance_m=MAX_ENDPOINT_SNAP_METERS,
            )
        if (
            incident["nearest_road_edge_hard_blocked"]
            and incident["nearest_road_edge_distance_m"]
            <= INCIDENT_EDGE_BLOCK_CHECK_METERS
        ):
            return _infeasible(
                "incident_access_edge_is_hard_blocked",
                scenario_id,
                facility_result,
                incident_result,
                hard_block_reason=incident["nearest_road_edge_block_reason"],
            )

        graph = _build_directed_graph(
            _load_scenario_edges(connection, scenario_id)
        )
        route = _compute_shortest_route(
            graph,
            int(facility["node_id"]),
            int(incident["node_id"]),
        )
        if route is None:
            return _infeasible(
                "no_safe_path",
                scenario_id,
                facility_result,
                incident_result,
            )

        return {
            "status": "feasible",
            "scenario_id": scenario_id,
            "scenario_hazard_type": incident["scenario_hazard_type"],
            "facility": facility_result,
            "incident": incident_result,
            "cost_function": "sum of unblocked edge travel_time",
            "soft_penalties_applied": False,
            "road_network_travel_time_seconds": route["travel_time_seconds"],
            "road_network_distance_meters": route["distance_meters"],
            "facility_and_incident_snap_access_distance_meters": (
                float(facility["snap_distance_m"])
                + float(incident["snap_distance_m"])
            ),
            "route": {
                "node_ids": route["node_ids"],
                "edge_ids": route["edge_ids"],
                "edges": route["edges"],
                "geometry": _route_geometry(
                    connection,
                    facility,
                    incident,
                    route,
                ),
            },
            "status_time_basis": (
                "Scenario edge status reflects any matching evidence during "
                "the complete event window, not current conditions."
            ),
        }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Route a DDMC station or hospital to an incident using the "
            "incident's scenario and excluding hard-blocked edges."
        )
    )
    parser.add_argument("--facility-id", required=True)
    parser.add_argument("--incident-record-id", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for a JSON result; otherwise print it to stdout.",
    )
    args = parser.parse_args()
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        result = route_rescue_dispatch(
            engine,
            args.facility_id,
            args.incident_record_id,
        )
    except (ValueError, OSError) as exc:
        print("Rescue routing failed: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output is None:
        print(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print("Route result written to {}".format(args.output))
        print("status={}".format(result["status"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
