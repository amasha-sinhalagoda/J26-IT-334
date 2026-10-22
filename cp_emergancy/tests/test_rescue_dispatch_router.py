import unittest

from scripts.route_rescue_dispatch import (
    MAX_ENDPOINT_SNAP_METERS,
    _build_directed_graph,
    _compute_shortest_route,
)


def edge(u, v, edge_id, travel_time, hard_blocked=False, length=100):
    return {
        "u": u,
        "v": v,
        "key": 0,
        "edge_id": edge_id,
        "travel_time": travel_time,
        "length": length,
        "hard_blocked": hard_blocked,
    }


class RescueDispatchRouterTests(unittest.TestCase):
    def test_minimizes_travel_time_with_directed_edges(self):
        graph = _build_directed_graph([
            edge(1, 2, "slow", 8),
            edge(1, 3, "fast-a", 2),
            edge(3, 2, "fast-b", 2),
            edge(2, 1, "reverse-only", 1),
        ])

        route = _compute_shortest_route(graph, 1, 2)

        self.assertEqual(["fast-a", "fast-b"], route["edge_ids"])
        self.assertEqual(4, route["travel_time_seconds"])
        self.assertEqual([1, 3, 2], route["node_ids"])

    def test_hard_blocked_edges_are_excluded(self):
        graph = _build_directed_graph([
            edge(1, 2, "blocked-shortcut", 1, hard_blocked=True),
            edge(1, 3, "safe-a", 3),
            edge(3, 2, "safe-b", 3),
        ])

        route = _compute_shortest_route(graph, 1, 2)

        self.assertEqual(["safe-a", "safe-b"], route["edge_ids"])
        self.assertNotIn("blocked-shortcut", route["edge_ids"])

    def test_selects_fastest_parallel_directed_edge(self):
        graph = _build_directed_graph([
            edge(1, 2, "parallel-slow", 4),
            edge(1, 2, "parallel-fast", 2),
        ])

        route = _compute_shortest_route(graph, 1, 2)

        self.assertEqual(["parallel-fast"], route["edge_ids"])
        self.assertEqual(2, route["travel_time_seconds"])

    def test_returns_no_route_for_unreachable_or_missing_nodes(self):
        graph = _build_directed_graph([edge(1, 2, "one-way", 1)])

        self.assertIsNone(_compute_shortest_route(graph, 2, 1))
        self.assertIsNone(_compute_shortest_route(graph, 1, 99))

    def test_rejects_invalid_travel_time(self):
        with self.assertRaises(ValueError):
            _build_directed_graph([edge(1, 2, "invalid", 0)])

    def test_exposes_endpoint_snap_limit(self):
        self.assertEqual(1000.0, MAX_ENDPOINT_SNAP_METERS)


if __name__ == "__main__":
    unittest.main()
