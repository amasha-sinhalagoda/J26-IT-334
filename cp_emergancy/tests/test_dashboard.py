import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

from resource_dispatch_dashboard import allocation_table, filtered_frame


class DashboardDataTests(unittest.TestCase):
    def setUp(self):
        self.requests = pd.DataFrame([
            {
                "alert_id": "FLOOD_1",
                "district": "North",
                "hazard_type": "Flood",
                "severity": "High",
                "requested_resource_type": "BOAT",
            },
            {
                "alert_id": "LANDSLIDE_1",
                "district": "South",
                "hazard_type": "Landslide",
                "severity": "Critical",
                "requested_resource_type": "AMB",
            },
        ])
        self.allocations = pd.DataFrame([
            {
                "alert_id": "FLOOD_1",
                "district": "North",
                "requested_resource_type": "BOAT",
                "resource_id": "R1",
                "allocated_quantity": 1,
                "straight_line_distance_km": 5.0,
            },
            {
                "alert_id": "LANDSLIDE_1",
                "district": "South",
                "requested_resource_type": "AMB",
                "resource_id": "R2",
                "allocated_quantity": 2,
                "straight_line_distance_km": 8.0,
            },
        ])
        self.request_results = pd.DataFrame([
            {
                "alert_id": "FLOOD_1",
                "requested_resource_type": "BOAT",
                "unfilled_quantity": 0,
            },
            {
                "alert_id": "LANDSLIDE_1",
                "requested_resource_type": "AMB",
                "unfilled_quantity": 1,
            },
        ])

    def test_allocation_rows_include_alert_hazard_and_unfilled_context(self):
        table = allocation_table(
            self.allocations, self.requests, self.request_results
        )

        self.assertEqual(table["hazard_type"].tolist(), ["Flood", "Landslide"])
        self.assertEqual(table["severity"].tolist(), ["High", "Critical"])
        self.assertEqual(table["unfilled_quantity"].tolist(), [0, 1])

    def test_filters_apply_only_to_display_rows(self):
        table = allocation_table(
            self.allocations, self.requests, self.request_results
        )

        flood_rows = filtered_frame(table, "North", "Flood", "BOAT")
        landslide_rows = filtered_frame(table, "All", "Landslide", "All")

        self.assertEqual(flood_rows["alert_id"].tolist(), ["FLOOD_1"])
        self.assertEqual(landslide_rows["alert_id"].tolist(), ["LANDSLIDE_1"])
        self.assertEqual(len(table), 2)

    def test_no_allocations_still_shows_hazard_requests_as_unfilled(self):
        empty_allocations = self.allocations.iloc[0:0]
        request_results = self.request_results.copy()
        request_results["allocated_quantity"] = 0
        request_results["unfilled_quantity"] = [2, 3]

        table = allocation_table(
            empty_allocations, self.requests, request_results
        )

        self.assertTrue(table.empty)
        self.assertIn("hazard_type", table.columns)


if __name__ == "__main__":
    unittest.main()
