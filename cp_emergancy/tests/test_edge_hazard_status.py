import unittest

from scripts.build_edge_hazard_status import (
    CLOSURE_NEAREST_REVIEW_METERS,
    INCIDENT_SNAP_BUFFER_METERS,
    _identifier,
)


class EdgeHazardStatusTests(unittest.TestCase):
    def test_spatial_tolerances_are_meters_and_review_only_for_closures(self):
        self.assertEqual(50, INCIDENT_SNAP_BUFFER_METERS)
        self.assertEqual(50, CLOSURE_NEAREST_REVIEW_METERS)

    def test_quotes_simple_sql_identifiers(self):
        self.assertEqual('"edge_scenario_status"', _identifier("edge_scenario_status"))

    def test_rejects_qualified_or_unsafe_identifiers(self):
        with self.assertRaises(ValueError):
            _identifier('dual_route"; DROP SCHEMA public;--')


if __name__ == "__main__":
    unittest.main()
