from pathlib import Path
import sys
import unittest


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

from build_road_graph import _edge_fingerprint, _normalize_oneway_tags


class FakeGraph:
    def __init__(self, edges):
        self._edges = edges

    def edges(self, keys, data):
        return [
            (u, v, key, attributes)
            for u, v, key, attributes in self._edges
        ]


class RoadGraphBuildTests(unittest.TestCase):
    def test_edge_id_is_stable_for_same_osm_edge(self):
        first = _edge_fingerprint(100, 200, 0, [77, 88])
        second = _edge_fingerprint(100, 200, 0, [88, 77])

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("osm-edge-"))

    def test_edge_id_distinguishes_direction_and_parallel_edges(self):
        forward = _edge_fingerprint(100, 200, 0, 77)
        reverse = _edge_fingerprint(200, 100, 0, 77)
        parallel = _edge_fingerprint(100, 200, 1, 77)

        self.assertEqual(len({forward, reverse, parallel}), 3)

    def test_oneway_tags_normalize_for_osmnx_graphml(self):
        graph = FakeGraph([
            (1, 2, 0, {"oneway": "yes"}),
            (2, 3, 0, {"oneway": "no"}),
            (3, 4, 0, {"oneway": "-1"}),
            (4, 5, 0, {"oneway": ["no", "no"]}),
            (5, 6, 0, {}),
        ])

        _normalize_oneway_tags(graph)

        self.assertEqual(
            [attributes["oneway"] for _, _, _, attributes in graph._edges],
            [True, False, True, False, False],
        )
        self.assertEqual(
            [attributes["oneway_osm"] for _, _, _, attributes in graph._edges],
            ["yes", "no", "-1", ["no", "no"], None],
        )


if __name__ == "__main__":
    unittest.main()
