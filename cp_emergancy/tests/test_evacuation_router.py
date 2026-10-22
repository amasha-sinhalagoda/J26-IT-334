import unittest

from scripts.route_evacuation import (
    _build_risk_weighted_graph,
    _build_sparse_routing_graph,
    _edge_cost,
    _optimal_capacity_assignment,
    _route_for_shelter,
    _risk_score,
)


def edge(
    u,
    v,
    edge_id,
    travel_time,
    hard_blocked=False,
    lhmp=None,
    incident_density=0,
    restricted=0,
    length=100,
):
    return {
        "u": u,
        "v": v,
        "edge_id": edge_id,
        "key": 0,
        "travel_time": travel_time,
        "length": length,
        "hard_blocked": hard_blocked,
        "max_lhmp_class": lhmp,
        "incident_density_per_km": incident_density,
        "restricted_closure_count": restricted,
    }


class EvacuationRouterTests(unittest.TestCase):
    def test_lhmp_risk_is_normalized_and_class_100_is_not_eligible(self):
        self.assertEqual(0.75, _risk_score(3, 0, 0))
        self.assertEqual(1.0, _risk_score(4, 0, 0))
        with self.assertRaises(ValueError):
            _risk_score(100, 0, 0)

    def test_incident_and_restricted_risk_are_bounded(self):
        self.assertEqual(0.4, _risk_score(None, 2, 0))
        self.assertEqual(0.5, _risk_score(None, 0, 1))
        self.assertEqual(1.0, _risk_score(None, 50, 1))

    def test_edge_cost_is_travel_time_times_one_plus_risk(self):
        self.assertEqual(150, _edge_cost(100, 0.5))
        with self.assertRaises(ValueError):
            _edge_cost(-1, 0.5)

    def test_graph_avoids_blocked_edges_and_uses_risk_weighted_cost(self):
        graph = _build_risk_weighted_graph([
            edge(1, 2, "fast-risky", 5, lhmp=4),
            edge(1, 3, "slower-safe-a", 6),
            edge(3, 2, "slower-safe-b", 6),
            edge(1, 2, "closed", 1, hard_blocked=True),
        ])

        self.assertNotIn("closed", [data["edge_id"] for _, _, data in graph.edges(data=True)])
        self.assertEqual(10, graph[1][2]["generalized_cost"])
        self.assertEqual(1.0, graph[1][2]["risk_score"])

    def test_sparse_route_reconstruction_preserves_direction_and_edge_ids(self):
        graph = _build_risk_weighted_graph([
            edge(1, 2, "blocked-direct", 1, hard_blocked=True),
            edge(1, 3, "open-a", 6),
            edge(3, 2, "open-b", 6),
        ])
        sparse_graph = _build_sparse_routing_graph(graph)
        cached_paths = {}

        route = _route_for_shelter(graph, sparse_graph, 1, 2, cached_paths)
        reverse_route = _route_for_shelter(
            graph, sparse_graph, 2, 1, cached_paths
        )

        self.assertEqual([1, 3, 2], route["node_ids"])
        self.assertEqual(["open-a", "open-b"], route["edge_ids"])
        self.assertIsNone(reverse_route)

    def test_capacity_assignment_minimizes_cost_without_overbooking(self):
        assignments = _optimal_capacity_assignment(
            {"origin-a": 4, "origin-b": 4},
            {"shelter-near": 4, "shelter-far": 4},
            {
                ("origin-a", "shelter-near"): 1,
                ("origin-a", "shelter-far"): 10,
                ("origin-b", "shelter-near"): 2,
                ("origin-b", "shelter-far"): 3,
            },
        )
        served = {
            (item["origin_id"], item["shelter_id"]): item["people_assigned"]
            for item in assignments
            if "shelter_id" in item
        }

        self.assertEqual(4, served[("origin-a", "shelter-near")])
        self.assertEqual(4, served[("origin-b", "shelter-far")])

    def test_flow_uses_available_capacity_and_reports_unassigned_demand(self):
        assignments = _optimal_capacity_assignment(
            {"origin-a": 7, "origin-b": 4},
            {"shelter-only": 5},
            {
                ("origin-a", "shelter-only"): 1,
                ("origin-b", "shelter-only"): 2,
            },
        )
        assigned = sum(
            item["people_assigned"]
            for item in assignments
            if "shelter_id" in item
        )
        unassigned = sum(
            item["people_unassigned"]
            for item in assignments
            if "people_unassigned" in item
        )

        self.assertEqual(5, assigned)
        self.assertEqual(6, unassigned)

    def test_rejects_fractional_people_and_capacity(self):
        with self.assertRaises(ValueError):
            _optimal_capacity_assignment({"origin-a": 1.5}, {}, {})
        with self.assertRaises(ValueError):
            _optimal_capacity_assignment({}, {"shelter-a": -1}, {})


if __name__ == "__main__":
    unittest.main()
