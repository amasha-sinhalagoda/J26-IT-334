import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch.comparison import compare_allocation_methods


class SameScenarioComparisonTests(unittest.TestCase):
    def test_methods_share_inputs_and_report_fulfillment_and_coverage(self):
        requests = pd.DataFrame([
            {
                "alert_id": "A",
                "district": "North",
                "requested_resource_type": "AMB",
                "requested_quantity": 2,
                "priority_score": 0.9,
                "priority_rank": 1,
                "local_scarcity_score": 0.0,
            },
            {
                "alert_id": "B",
                "district": "South",
                "requested_resource_type": "AMB",
                "requested_quantity": 2,
                "priority_score": 0.7,
                "priority_rank": 2,
                "local_scarcity_score": 1.0,
            },
        ])
        supply = pd.DataFrame([
            {"resource_id": "R1", "resource_type": "AMB", "available_count": 2},
        ])
        candidates = pd.DataFrame([
            {
                "alert_id": "A",
                "requested_resource_type": "AMB",
                "requested_quantity": 2,
                "priority_score": 0.9,
                "priority_rank": 1,
                "local_scarcity_score": 0.0,
                "resource_id": "R1",
                "candidate_resource_type": "AMB",
                "available_quantity": 2,
                "straight_line_distance_km": 1.0,
                "district": "North",
                "GN_division": "N1",
                "resource_district": "North",
                "is_same_district": True,
            },
            {
                "alert_id": "B",
                "requested_resource_type": "AMB",
                "requested_quantity": 2,
                "priority_score": 0.7,
                "priority_rank": 2,
                "local_scarcity_score": 1.0,
                "resource_id": "R1",
                "candidate_resource_type": "AMB",
                "available_quantity": 2,
                "straight_line_distance_km": 10.0,
                "district": "South",
                "GN_division": "S1",
                "resource_district": "North",
                "is_same_district": False,
            },
        ])

        result = compare_allocation_methods(requests, supply, candidates)

        self.assertEqual(
            result["method_summary"]["method"].tolist(),
            ["greedy_nearest", "cp_sat_optimizer"],
        )
        self.assertEqual(len(result["request_comparison"]), 2)
        self.assertEqual(len(result["resource_type_metrics"]), 2)
        for method_name in ["greedy", "optimizer"]:
            method = result[method_name]
            self.assertEqual(
                int(method["allocations"]["allocated_quantity"].sum()), 2
            )
            self.assertGreaterEqual(
                int(method["resource_results"].iloc[0]["remaining_quantity"]), 0
            )
            self.assertLessEqual(
                int(method["request_results"]["allocated_quantity"].max()), 2
            )
        self.assertEqual(
            result["method_summary"]["alerted_districts"].tolist(), [2, 2]
        )
        self.assertEqual(
            result["method_summary"]["dispatch_score_weighted_units"].tolist(),
            [1.52, 1.52],
        )
        self.assertEqual(
            result["method_summary"][
                "straight_line_quantity_distance_km"
            ].tolist(),
            [20.0, 20.0],
        )

        empty_scenario = compare_allocation_methods(
            requests.iloc[0:0], supply.iloc[0:0], candidates.iloc[0:0]
        )
        self.assertEqual(len(empty_scenario["method_summary"]), 2)
        self.assertTrue(empty_scenario["request_comparison"].empty)
        self.assertEqual(
            empty_scenario["method_summary"]["alerted_districts"].tolist(),
            [0, 0],
        )

        unserved = compare_allocation_methods(
            requests, supply, candidates.iloc[0:0]
        )
        for method_name in ["greedy", "optimizer"]:
            self.assertTrue(unserved[method_name]["allocations"].empty)
            self.assertEqual(
                int(
                    unserved[method_name]["request_results"][
                        "unfilled_quantity"
                    ].sum()
                ),
                4,
            )

    def test_resource_type_metrics_keep_unit_types_separate(self):
        requests = pd.DataFrame([
            {
                "alert_id": "AMB_ALERT",
                "district": "North",
                "requested_resource_type": "AMB",
                "requested_quantity": 1,
                "priority_score": 0.8,
                "priority_rank": 1,
                "local_scarcity_score": 0.5,
            },
            {
                "alert_id": "SHELTER_ALERT",
                "district": "South",
                "requested_resource_type": "SHL",
                "requested_quantity": 100,
                "priority_score": 0.7,
                "priority_rank": 2,
                "local_scarcity_score": 0.2,
            },
        ])
        supply = pd.DataFrame([
            {"resource_id": "AMB1", "resource_type": "AMB", "available_count": 1},
            {"resource_id": "SHL1", "resource_type": "SHL", "available_count": 80},
        ])
        candidates = pd.DataFrame([
            {
                "alert_id": "AMB_ALERT",
                "requested_resource_type": "AMB",
                "requested_quantity": 1,
                "priority_score": 0.8,
                "priority_rank": 1,
                "local_scarcity_score": 0.5,
                "resource_id": "AMB1",
                "candidate_resource_type": "AMB",
                "available_quantity": 1,
                "straight_line_distance_km": 1.0,
                "district": "North",
            },
            {
                "alert_id": "SHELTER_ALERT",
                "requested_resource_type": "SHL",
                "requested_quantity": 100,
                "priority_score": 0.7,
                "priority_rank": 2,
                "local_scarcity_score": 0.2,
                "resource_id": "SHL1",
                "candidate_resource_type": "SHL",
                "available_quantity": 80,
                "straight_line_distance_km": 2.0,
                "district": "South",
            },
        ])

        result = compare_allocation_methods(requests, supply, candidates)
        metrics = result["resource_type_metrics"]

        self.assertEqual(set(metrics["requested_resource_type"]), {"AMB", "SHL"})
        self.assertFalse(
            result["method_summary"].columns.isin(
                ["requested_quantity", "allocated_quantity"]
            ).any()
        )


if __name__ == "__main__":
    unittest.main()
