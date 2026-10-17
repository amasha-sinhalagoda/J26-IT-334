import sys
import unittest

from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch.evaluation import (
    evaluate_district_coverage,
    evaluate_historical_dispatch,
)


class DispatchEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.requests = pd.DataFrame([
            {
                "alert_id": "A",
                "district": "North",
                "requested_resource_type": "AMB",
                "requested_quantity": 2,
                "timestamp": "2025-11-27 10:00:00",
                "local_scarcity_score": 0.5,
            },
            {
                "alert_id": "B",
                "district": "South",
                "requested_resource_type": "AMB",
                "requested_quantity": 1,
                "timestamp": "2025-11-27 10:00:00",
                "local_scarcity_score": 1.0,
            },
            {
                "alert_id": "C",
                "district": "East",
                "requested_resource_type": "RT",
                "requested_quantity": 1,
                "timestamp": "2025-11-27 10:00:00",
                "local_scarcity_score": 0.0,
            },
        ])

    def test_coverage_reports_total_and_scarcity_districts(self):
        services = pd.DataFrame([
            {
                "district": "North",
                "requested_resource_type": "AMB",
                "allocated_quantity": 1,
            },
            {
                "district": "East",
                "requested_resource_type": "RT",
                "allocated_quantity": 1,
            },
        ])

        result = evaluate_district_coverage(
            self.requests,
            services,
            district_column="district",
            resource_type_column="requested_resource_type",
            quantity_column="allocated_quantity",
        )

        self.assertEqual(result["alerted_districts"], 3)
        self.assertEqual(result["districts_covered"], 2)
        self.assertAlmostEqual(result["district_coverage_rate"], 2 / 3)
        self.assertEqual(result["scarce_districts"], 2)
        self.assertEqual(result["scarce_districts_covered"], 1)
        self.assertEqual(result["scarcity_district_coverage_rate"], 0.5)

    def test_historical_metrics_apply_response_window_and_detect_overlapping_reuse(self):
        assignments = pd.DataFrame([
            {
                "alert_id": "A",
                "resource_id": "R1",
                "resource_type": "AMB",
                "assigned_quantity": 1,
                "assignment_time": "2025-11-27 10:00:00",
                "estimated_arrival": "2025-11-27 10:20:00",
                "status_time": "2025-11-27 11:00:00",
            },
            {
                "alert_id": "B",
                "resource_id": "R1",
                "resource_type": "AMB",
                "assigned_quantity": 1,
                "assignment_time": "2025-11-27 10:10:00",
                "estimated_arrival": "2025-11-27 10:30:00",
                "status_time": "2025-11-27 11:10:00",
            },
            {
                "alert_id": "C",
                "resource_id": "R2",
                "resource_type": "RT",
                "assigned_quantity": 1,
                "assignment_time": "2025-11-27 10:00:00",
                "estimated_arrival": "2025-11-27 10:40:00",
                "status_time": "2025-11-27 11:00:00",
            },
        ])

        result = evaluate_historical_dispatch(
            self.requests, assignments, first_response_window_minutes=25
        )

        self.assertEqual(result["assignments_in_window"], 1)
        self.assertEqual(result["assignment_count"], 3)
        self.assertEqual(result["concurrent_reuse_rows"], 2)
        self.assertAlmostEqual(result["concurrent_reuse_rate"], 2 / 3)
        self.assertEqual(
            result["district_coverage"]["scarce_districts_covered"], 1
        )
        self.assertAlmostEqual(
            result["district_coverage"]["district_coverage_rate"], 1 / 3
        )
        self.assertIn("proxy", result["concurrent_reuse_definition"])

    def test_historical_evaluation_requires_positive_response_window(self):
        with self.assertRaisesRegex(ValueError, "positive number"):
            evaluate_historical_dispatch(
                self.requests, pd.DataFrame(), first_response_window_minutes=0
            )

    def test_coverage_rejects_invalid_scarcity_scores(self):
        requests = self.requests.copy()
        requests.loc[0, "local_scarcity_score"] = 1.1

        with self.assertRaisesRegex(ValueError, "between 0 and 1"):
            evaluate_district_coverage(
                requests,
                pd.DataFrame(columns=[
                    "district", "requested_resource_type", "allocated_quantity",
                ]),
                district_column="district",
                resource_type_column="requested_resource_type",
                quantity_column="allocated_quantity",
            )


if __name__ == "__main__":
    unittest.main()
