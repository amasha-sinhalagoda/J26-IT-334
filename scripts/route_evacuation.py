import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import sys

import networkx as nx
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra
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
BLOCKED_ENDPOINT_ACCESS_METERS = 50.0
INCIDENT_DENSITY_SATURATION_PER_KM = 5.0
RISK_COST_SCALE = 1000
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


def _risk_score(max_lhmp_class, incident_density_per_km, restricted_closure_count):
    component_scores = [0.0]
    if max_lhmp_class is not None:
        if max_lhmp_class not in (3, 4):
            raise ValueError(
                "Only LHMP classes 3 and 4 are risk-eligible, got {}".format(
                    max_lhmp_class
                )
            )
        component_scores.append(float(max_lhmp_class) / 4.0)
    if incident_density_per_km is not None:
        density = float(incident_density_per_km)
        if not math.isfinite(density) or density < 0:
            raise ValueError("Invalid incident density: {}".format(density))
        component_scores.append(
            min(density / INCIDENT_DENSITY_SATURATION_PER_KM, 1.0)
        )
    if restricted_closure_count:
        component_scores.append(0.5)
    return max(component_scores)


def _edge_cost(travel_time, risk_score):
    travel_time = float(travel_time)
    risk_score = float(risk_score)
    if not math.isfinite(travel_time) or travel_time <= 0:
        raise ValueError("Edge travel_time must be finite and positive")
    if not math.isfinite(risk_score) or not 0 <= risk_score <= 1:
        raise ValueError("Edge risk_score must be finite and in [0, 1]")
    return travel_time * (1 + risk_score)


def _build_risk_weighted_graph(edge_rows):
    graph = nx.DiGraph()
    for row in edge_rows:
        if row["hard_blocked"]:
            continue
        travel_time = float(row["travel_time"])
        length = float(row["length"])
        if not math.isfinite(length) or length < 0:
            raise ValueError(
                "Edge {} has invalid length {}".format(row["edge_id"], length)
            )
        max_lhmp_class = row["max_lhmp_class"]
        if max_lhmp_class is not None:
            max_lhmp_class = int(max_lhmp_class)
        risk = _risk_score(
            max_lhmp_class,
            row["incident_density_per_km"],
            row["restricted_closure_count"],
        )
        generalized_cost = _edge_cost(travel_time, risk)
        start = int(row["u"])
        end = int(row["v"])
        current = graph.get_edge_data(start, end)
        if current is None or generalized_cost < current["generalized_cost"]:
            graph.add_edge(
                start,
                end,
                edge_id=row["edge_id"],
                key=int(row["key"]),
                travel_time=travel_time,
                generalized_cost=generalized_cost,
                risk_score=risk,
                length=length,
            )
    return graph


def _build_sparse_routing_graph(graph):
    nodes = sorted(graph.nodes())
    node_indexes = {node: index for index, node in enumerate(nodes)}
    rows = []
    columns = []
    weights = []
    for start, end, data in graph.edges(data=True):
        rows.append(node_indexes[start])
        columns.append(node_indexes[end])
        weights.append(data["generalized_cost"])
    matrix = csr_matrix(
        (weights, (rows, columns)),
        shape=(len(nodes), len(nodes)),
    )
    return matrix, nodes, node_indexes


def _optimal_capacity_assignment(demands, capacities, candidate_costs):
    source = ("terminal", "origin")
    sink = ("terminal", "shelter")
    flow_graph = nx.DiGraph()
    flow_graph.add_node(source)
    flow_graph.add_node(sink)

    for origin_id, demand in demands.items():
        if not isinstance(demand, int) or isinstance(demand, bool) or demand <= 0:
            raise ValueError(
                "Demand for {} must be a positive whole number".format(origin_id)
            )
        origin_node = ("origin", origin_id)
        flow_graph.add_edge(source, origin_node, capacity=demand, weight=0)

    for shelter_id, capacity in capacities.items():
        if (
            not isinstance(capacity, int)
            or isinstance(capacity, bool)
            or capacity < 0
        ):
            raise ValueError(
                "Capacity for {} must be a non-negative whole number".format(
                    shelter_id
                )
            )
        flow_graph.add_edge(("shelter", shelter_id), sink, capacity=capacity, weight=0)

    for (origin_id, shelter_id), generalized_cost in candidate_costs.items():
        if origin_id not in demands or shelter_id not in capacities:
            raise ValueError("Candidate route references an unknown origin or shelter")
        if not math.isfinite(float(generalized_cost)) or generalized_cost < 0:
            raise ValueError("Candidate cost must be finite and non-negative")
        integer_cost = int(round(float(generalized_cost) * RISK_COST_SCALE))
        flow_graph.add_edge(
            ("origin", origin_id),
            ("shelter", shelter_id),
            capacity=demands[origin_id],
            weight=integer_cost,
        )

    flow = nx.max_flow_min_cost(
        flow_graph,
        source,
        sink,
        capacity="capacity",
        weight="weight",
    )
    assignments = []
    for origin_id in demands:
        assigned = 0
        for shelter_id in capacities:
            amount = flow.get(("origin", origin_id), {}).get(
                ("shelter", shelter_id), 0
            )
            if amount:
                assigned += amount
                assignments.append({
                    "origin_id": origin_id,
                    "shelter_id": shelter_id,
                    "people_assigned": amount,
                })
        assignments.append({
            "origin_id": origin_id,
            "people_unassigned": demands[origin_id] - assigned,
        })
    return assignments


def _infeasible(reason, origin, **details):
    result = {
        "status": "infeasible",
        "reason": reason,
        "origin_id": origin["origin_id"],
        "scenario_id": origin["scenario_id"],
        "destination": None,
        "route": None,
    }
    result.update(details)
    return result


def _load_scenario(connection, scenario_id):
    row = connection.execute(text("""
        SELECT scenario_id, event_id, district, hazard_type, started_at, ended_at
        FROM dual_route.events
        WHERE scenario_id = :scenario_id
    """), {"scenario_id": scenario_id}).mappings().first()
    if row is None:
        raise ValueError("Unknown scenario_id: {}".format(scenario_id))
    return dict(row)


def _load_origins(connection, scenario_id):
    rows = connection.execute(text("""
        SELECT
            origin.origin_id,
            origin.scenario_id,
            origin.district,
            origin.origin_type,
            origin.gn_code,
            origin.affected_people,
            origin.at_risk_units,
            origin.source_type,
            origin.is_synthetic,
            ST_X(origin.geometry) AS point_x,
            ST_Y(origin.geometry) AS point_y,
            nearest.node_id,
            nearest.distance_m AS snap_distance_m,
            nearest_edge.edge_id AS nearest_road_edge_id,
            nearest_edge.distance_m AS nearest_road_edge_distance_m
        FROM dual_route.evacuation_origins AS origin
        CROSS JOIN LATERAL (
            SELECT
                node.osmid AS node_id,
                ST_Distance(node.geometry, origin.geometry) AS distance_m
            FROM dual_route.road_nodes AS node
            ORDER BY node.geometry <-> origin.geometry, node.osmid
            LIMIT 1
        ) AS nearest
        CROSS JOIN LATERAL (
            SELECT
                edge.edge_id,
                ST_Distance(edge.geometry, origin.geometry) AS distance_m
            FROM dual_route.road_edges AS edge
            ORDER BY edge.geometry <-> origin.geometry, edge.edge_id
            LIMIT 1
        ) AS nearest_edge
        WHERE origin.scenario_id = :scenario_id
        ORDER BY origin.origin_id
    """), {"scenario_id": scenario_id}).mappings().all()
    return [dict(row) for row in rows]


def _load_shelters(connection):
    rows = connection.execute(text("""
        SELECT
            shelter.shelter_id,
            shelter.district,
            shelter.name,
            shelter.total_capacity,
            shelter.available_capacity,
            lower(shelter.operational_status::text) AS operational_status,
            shelter.source_type,
            shelter.is_synthetic,
            ST_X(shelter.geometry) AS point_x,
            ST_Y(shelter.geometry) AS point_y,
            nearest.node_id,
            nearest.distance_m AS snap_distance_m,
            nearest_edge.edge_id AS nearest_road_edge_id,
            nearest_edge.distance_m AS nearest_road_edge_distance_m
        FROM dual_route.shelters AS shelter
        CROSS JOIN LATERAL (
            SELECT
                node.osmid AS node_id,
                ST_Distance(node.geometry, shelter.geometry) AS distance_m
            FROM dual_route.road_nodes AS node
            ORDER BY node.geometry <-> shelter.geometry, node.osmid
            LIMIT 1
        ) AS nearest
        CROSS JOIN LATERAL (
            SELECT
                edge.edge_id,
                ST_Distance(edge.geometry, shelter.geometry) AS distance_m
            FROM dual_route.road_edges AS edge
            ORDER BY edge.geometry <-> shelter.geometry, edge.edge_id
            LIMIT 1
        ) AS nearest_edge
        WHERE lower(shelter.operational_status::text) = 'open'
          AND shelter.available_capacity > 0
        ORDER BY shelter.shelter_id
    """)).mappings().all()
    return [dict(row) for row in rows]


def _load_scenario_edges(connection, scenario_id):
    rows = connection.execute(text("""
        WITH scenario_event AS (
            SELECT event_id, scenario_id, started_at, ended_at
            FROM dual_route.events
            WHERE scenario_id = :scenario_id
        ),
        scenario_hazards AS (
            SELECT
                hit.edge_id,
                count(*)::integer AS hard_hazard_count
            FROM dual_route.edge_hazard_matches AS hit
            JOIN scenario_event AS event
              ON event.event_id = hit.event_id
             AND event.scenario_id = hit.scenario_id
            WHERE hit.valid_from <= event.ended_at
              AND hit.valid_to >= event.started_at
            GROUP BY hit.edge_id
        ),
        scenario_closures AS (
            SELECT
                hit.edge_id,
                count(*) FILTER (WHERE hit.status = 'closed')::integer
                    AS closed_closure_count,
                count(*) FILTER (WHERE hit.status = 'restricted')::integer
                    AS restricted_closure_count
            FROM dual_route.edge_closure_matches AS hit
            JOIN scenario_event AS event
              ON event.event_id = hit.event_id
             AND event.scenario_id = hit.scenario_id
            WHERE hit.valid_from <= event.ended_at
              AND hit.valid_to >= event.started_at
            GROUP BY hit.edge_id
        )
        SELECT
            edge.u,
            edge.v,
            edge.key,
            edge.edge_id,
            edge.travel_time,
            edge.length,
            (
                coalesce(hazard.hard_hazard_count, 0) > 0
                OR coalesce(closure.closed_closure_count, 0) > 0
            ) AS hard_blocked,
            risk.max_lhmp_class,
            risk.incident_density_per_km,
            coalesce(closure.restricted_closure_count, 0)::integer
                AS restricted_closure_count
        FROM dual_route.road_edges AS edge
        JOIN dual_route.edge_static_risk AS risk USING (edge_id)
        LEFT JOIN scenario_hazards AS hazard USING (edge_id)
        LEFT JOIN scenario_closures AS closure USING (edge_id)
    """), {"scenario_id": scenario_id}).mappings()
    return list(rows)


def _node_coordinates(connection, node_ids):
    if not node_ids:
        return {}
    rows = connection.execute(text("""
        SELECT osmid, ST_X(geometry) AS x, ST_Y(geometry) AS y
        FROM dual_route.road_nodes
        WHERE osmid = ANY(:node_ids)
    """), {"node_ids": list(node_ids)}).mappings()
    return {
        int(row["osmid"]): (float(row["x"]), float(row["y"]))
        for row in rows
    }


def _route_geometry(connection, origin, shelter, route):
    global ENDPOINT_TRANSFORMER
    if ENDPOINT_TRANSFORMER is None:
        from pyproj import Transformer

        ENDPOINT_TRANSFORMER = Transformer.from_crs(
            "EPSG:{}".format(TARGET_SRID),
            "EPSG:4326",
            always_xy=True,
        )
    nodes = _node_coordinates(connection, route["node_ids"])
    projected = [(origin["point_x"], origin["point_y"])]
    projected.extend(nodes[node_id] for node_id in route["node_ids"])
    projected.append((shelter["point_x"], shelter["point_y"]))
    coordinates = [
        list(ENDPOINT_TRANSFORMER.transform(x, y))
        for x, y in projected
    ]
    return {"type": "LineString", "coordinates": coordinates}


def _route_for_shelter(graph, sparse_graph, source, target, cached_paths):
    matrix, nodes, node_indexes = sparse_graph
    if source not in cached_paths:
        if source not in node_indexes:
            cached_paths[source] = (None, None)
        else:
            distances, predecessors = dijkstra(
                matrix,
                directed=True,
                indices=node_indexes[source],
                return_predecessors=True,
            )
            cached_paths[source] = (distances, predecessors)
    distances, predecessors = cached_paths[source]
    if target not in node_indexes or distances is None:
        return None

    target_index = node_indexes[target]
    if not math.isfinite(float(distances[target_index])):
        return None
    route_indexes = [target_index]
    while route_indexes[-1] != node_indexes[source]:
        predecessor = int(predecessors[route_indexes[-1]])
        if predecessor < 0:
            return None
        route_indexes.append(predecessor)
    route_indexes.reverse()
    route_nodes = [nodes[index] for index in route_indexes]
    edges = []
    total_time = 0.0
    generalized_cost = 0.0
    total_length = 0.0
    for start, end in zip(route_nodes, route_nodes[1:]):
        edge = graph[start][end]
        total_time += edge["travel_time"]
        generalized_cost += edge["generalized_cost"]
        total_length += edge["length"]
        edges.append({
            "edge_id": edge["edge_id"],
            "from_node": start,
            "to_node": end,
            "key": edge["key"],
            "travel_time_seconds": edge["travel_time"],
            "risk_score": edge["risk_score"],
            "generalized_cost_seconds": edge["generalized_cost"],
            "length_meters": edge["length"],
        })
    return {
        "node_ids": route_nodes,
        "edges": edges,
        "edge_ids": [edge["edge_id"] for edge in edges],
        "travel_time_seconds": total_time,
        "generalized_cost_seconds": generalized_cost,
        "distance_meters": total_length,
    }


def _whole_person_demand(origin):
    value = origin["affected_people"]
    if value is None:
        return None
    demand = float(value)
    if not math.isfinite(demand) or demand < 0 or not demand.is_integer():
        raise ValueError(
            "Origin {} affected_people must be a non-negative whole number".format(
                origin["origin_id"]
            )
        )
    return int(demand)


def plan_evacuation(engine, scenario_id):
    with engine.connect() as connection:
        scenario = _load_scenario(connection, scenario_id)
        origins = _load_origins(connection, scenario_id)
        if not origins:
            raise ValueError(
                "Scenario {} has no evacuation origins".format(scenario_id)
            )

        origin_results = []
        routable_origins = {}
        demands = {}
        for origin in origins:
            demand = _whole_person_demand(origin)
            origin_result = {
                "origin_id": origin["origin_id"],
                "district": origin["district"],
                "origin_type": origin["origin_type"],
                "gn_code": origin["gn_code"],
                "affected_people": demand,
                "demand_status": "known" if demand is not None else "unknown",
                "source_type": origin["source_type"],
                "is_synthetic": origin["is_synthetic"],
                "network_snap_distance_m": float(origin["snap_distance_m"]),
                "nearest_road_edge_id": (
                    origin["nearest_road_edge_id"]
                    if "nearest_road_edge_id" in origin
                    else None
                ),
                "nearest_road_edge_distance_m": (
                    float(origin["nearest_road_edge_distance_m"])
                    if origin.get("nearest_road_edge_distance_m") is not None
                    else None
                ),
                "assignments": [],
            }
            origin_results.append(origin_result)
            if demand is None:
                origin_result["status"] = "infeasible"
                origin_result["reason"] = "affected_people_unknown"
                continue
            if demand == 0:
                origin_result["status"] = "feasible"
                origin_result["reason"] = "zero_evacuation_demand"
                continue
            if origin["snap_distance_m"] > MAX_ENDPOINT_SNAP_METERS:
                origin_result["status"] = "infeasible"
                origin_result["reason"] = "origin_too_far_from_road_network"
                origin_result["people_unassigned"] = demand
                continue
            routable_origins[origin["origin_id"]] = origin
            demands[origin["origin_id"]] = demand

        result_by_origin = {
            result["origin_id"]: result for result in origin_results
        }
        shelters = _load_shelters(connection) if demands else []
        edge_rows = (
            _load_scenario_edges(connection, scenario_id)
            if demands and shelters
            else []
        )
        hard_blocked_edge_ids = {
            row["edge_id"] for row in edge_rows if row["hard_blocked"]
        }
        for origin_id in list(routable_origins):
            origin = routable_origins[origin_id]
            nearest_edge_id = origin.get("nearest_road_edge_id")
            edge_distance = origin.get("nearest_road_edge_distance_m")
            if (
                nearest_edge_id in hard_blocked_edge_ids
                and edge_distance is not None
                and edge_distance <= BLOCKED_ENDPOINT_ACCESS_METERS
            ):
                result_by_origin[origin_id]["status"] = "infeasible"
                result_by_origin[origin_id]["reason"] = (
                    "origin_access_edge_is_hard_blocked"
                )
                result_by_origin[origin_id]["people_unassigned"] = demands.pop(
                    origin_id
                )
                del routable_origins[origin_id]

        available_shelters = {}
        for shelter in shelters:
            if shelter["snap_distance_m"] > MAX_ENDPOINT_SNAP_METERS:
                continue
            nearest_edge_id = shelter["nearest_road_edge_id"]
            edge_distance = shelter["nearest_road_edge_distance_m"]
            if (
                nearest_edge_id in hard_blocked_edge_ids
                and edge_distance <= BLOCKED_ENDPOINT_ACCESS_METERS
            ):
                continue
            capacity = int(shelter["available_capacity"])
            if capacity > 0:
                available_shelters[shelter["shelter_id"]] = shelter

        graph = _build_risk_weighted_graph(edge_rows)
        sparse_graph = _build_sparse_routing_graph(graph)

        candidate_routes = {}
        route_details = {}
        reachable_origins = set()
        cached_paths = {}
        for origin_id, origin in routable_origins.items():
            origin_node = int(origin["node_id"])
            for shelter_id, shelter in available_shelters.items():
                route = _route_for_shelter(
                    graph,
                    sparse_graph,
                    origin_node,
                    int(shelter["node_id"]),
                    cached_paths,
                )
                if route is None:
                    continue
                reachable_origins.add(origin_id)
                key = (origin_id, shelter_id)
                candidate_routes[key] = route["generalized_cost_seconds"]
                route_details[key] = route

        capacities = {
            shelter_id: int(shelter["available_capacity"])
            for shelter_id, shelter in available_shelters.items()
        }
        assignments = _optimal_capacity_assignment(
            demands,
            capacities,
            candidate_routes,
        ) if demands else []
        assignment_summary = {}
        for assignment in assignments:
            origin_id = assignment["origin_id"]
            if "shelter_id" not in assignment:
                result_by_origin[origin_id]["people_unassigned"] = assignment[
                    "people_unassigned"
                ]
                continue
            shelter_id = assignment["shelter_id"]
            origin = routable_origins[origin_id]
            shelter = available_shelters[shelter_id]
            route = route_details[(origin_id, shelter_id)]
            result_by_origin[origin_id]["assignments"].append({
                "shelter_id": shelter_id,
                "shelter_name": shelter["name"],
                "shelter_district": shelter["district"],
                "people_assigned": assignment["people_assigned"],
                "shelter_capacity_before_plan": int(
                    shelter["available_capacity"]
                ),
                "route_cost_seconds_per_person": route[
                    "generalized_cost_seconds"
                ],
                "travel_time_seconds": route["travel_time_seconds"],
                "distance_meters": route["distance_meters"],
                "route": {
                    "node_ids": route["node_ids"],
                    "edge_ids": route["edge_ids"],
                    "edges": route["edges"],
                    "geometry": _route_geometry(
                        connection,
                        origin,
                        shelter,
                        route,
                    ),
                },
            })
            summary = assignment_summary.setdefault(
                shelter_id,
                {
                    "shelter_id": shelter_id,
                    "shelter_name": shelter["name"],
                    "district": shelter["district"],
                    "available_capacity": int(shelter["available_capacity"]),
                    "people_assigned": 0,
                },
            )
            summary["people_assigned"] += assignment["people_assigned"]

        known_demand = sum(
            demand
            for origin in origins
            for demand in [_whole_person_demand(origin)]
            if demand is not None
        )
        people_assigned = sum(
            item["people_assigned"] for item in assignment_summary.values()
        )
        for result in origin_results:
            if result.get("status") is not None:
                continue
            assigned = sum(
                item["people_assigned"] for item in result["assignments"]
            )
            unassigned = int(result.get("people_unassigned", 0))
            result["people_assigned"] = assigned
            result["people_unassigned"] = unassigned
            if assigned + unassigned != result["affected_people"]:
                raise ValueError(
                    "Origin {} assignment does not reconcile with demand".format(
                        result["origin_id"]
                    )
                )
            result["status"] = (
                "feasible"
                if unassigned == 0
                else "partial"
                if assigned > 0
                else "infeasible"
            )
            if unassigned:
                result["reason"] = (
                    "insufficient_reachable_shelter_capacity"
                    if result["origin_id"] in reachable_origins
                    else "no_safe_path_to_available_shelter"
                )
            else:
                result["reason"] = None

        statuses = [item["status"] for item in origin_results]
        overall_status = (
            "infeasible"
            if not people_assigned
            else "partial"
            if any(status != "feasible" for status in statuses)
            else "feasible"
        )
        return {
            "status": overall_status,
            "scenario": {
                "scenario_id": scenario["scenario_id"],
                "event_id": scenario["event_id"],
                "district": scenario["district"],
                "hazard_type": scenario["hazard_type"],
                "started_at": scenario["started_at"],
                "ended_at": scenario["ended_at"],
            },
            "cost_function": (
                "edge travel_time_seconds * (1 + edge risk_score); "
                "minimize total assigned person-cost after maximizing "
                "capacity-feasible people served"
            ),
            "risk_model": {
                "range": [0.0, 1.0],
                "combination": "maximum eligible edge signal; no evidence is summed",
                "lhmp_class_3": 0.75,
                "lhmp_class_4": 1.0,
                "incident_density_component": (
                    "min(incident_count_50m_per_km / 5, 1)"
                ),
                "restricted_closure_component": 0.5,
                "hard_blocks": "excluded before shortest-path search",
            },
            "status_time_basis": (
                "Scenario edge status reflects any matching evidence during "
                "the complete event window, not current conditions."
            ),
            "demand": {
                "origin_count": len(origins),
                "known_people": known_demand,
                "unknown_demand_origin_count": sum(
                    result["demand_status"] == "unknown"
                    for result in origin_results
                ),
                "served_people": people_assigned,
                "unserved_known_people": known_demand - people_assigned,
                "unknown_demand_policy": (
                    "Do not infer persons from at_risk_units or origin count; "
                    "leave such origins unassigned until affected_people is supplied."
                ),
            },
            "shelter_assignments": list(assignment_summary.values()),
            "origins": origin_results,
        }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Build a capacity-constrained, risk-aware evacuation plan "
            "for one scenario."
        )
    )
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional path for JSON result; otherwise print to stdout.",
    )
    args = parser.parse_args()
    engine = create_engine(database_url(), pool_pre_ping=True)
    try:
        result = plan_evacuation(engine, args.scenario_id)
    except (ValueError, OSError) as exc:
        print("Evacuation routing failed: {}".format(exc), file=sys.stderr)
        return 1
    finally:
        engine.dispose()

    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output is None:
        print(rendered)
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print("Evacuation plan written to {}".format(args.output))
        print(
            "status={} served_people={} unserved_known_people={}".format(
                result["status"],
                result["demand"]["served_people"],
                result["demand"]["unserved_known_people"],
            )
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
