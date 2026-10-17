import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch import solve_allocation


class AllocationSolverTests(unittest.TestCase):
    def test_priority_weighting_reserves_scarce_supply_for_higher_priority(self):
        requests = pd.DataFrame([
            {"alert_id": "A", "requested_resource_type": "AMB", "requested_quantity": 2, "priority_score": 0.9, "priority_rank": 1},
            {"alert_id": "B", "requested_resource_type": "AMB", "requested_quantity": 2, "priority_score": 0.5, "priority_rank": 2},
        ])
        supply = pd.DataFrame([
            {"resource_id": "R1", "resource_type": "AMB", "available_count": 2},
        ])
        candidates = pd.DataFrame([
            {"alert_id": "A", "requested_resource_type": "AMB", "requested_quantity": 2, "priority_score": 0.9, "resource_id": "R1", "candidate_resource_type": "AMB", "available_quantity": 2, "straight_line_distance_km": 10.0},
            {"alert_id": "B", "requested_resource_type": "AMB", "requested_quantity": 2, "priority_score": 0.5, "resource_id": "R1", "candidate_resource_type": "AMB", "available_quantity": 2, "straight_line_distance_km": 1.0},
        ])

        result = solve_allocation(requests, supply, candidates)
        allocated = result["request_results"].set_index("alert_id")["allocated_quantity"]

        self.assertEqual(int(allocated["A"]), 2)
        self.assertEqual(int(allocated["B"]), 0)
        self.assertEqual(int(result["resource_results"].iloc[0]["remaining_quantity"]), 0)

    def test_distance_breaks_ties_after_priority_objective(self):
        requests = pd.DataFrame([
            {"alert_id": "A", "requested_resource_type": "RT", "requested_quantity": 1, "priority_score": 0.7, "priority_rank": 1},
        ])
        supply = pd.DataFrame([
            {"resource_id": "CLOSE", "resource_type": "RT", "available_count": 1},
            {"resource_id": "FAR", "resource_type": "RT", "available_count": 1},
        ])
        candidates = pd.DataFrame([
            {"alert_id": "A", "requested_resource_type": "RT", "requested_quantity": 1, "priority_score": 0.7, "resource_id": "CLOSE", "candidate_resource_type": "RT", "available_quantity": 1, "straight_line_distance_km": 2.0},
            {"alert_id": "A", "requested_resource_type": "RT", "requested_quantity": 1, "priority_score": 0.7, "resource_id": "FAR", "candidate_resource_type": "RT", "available_quantity": 1, "straight_line_distance_km": 15.0},
        ])

        result = solve_allocation(requests, supply, candidates)

        self.assertEqual(result["allocations"]["resource_id"].tolist(), ["CLOSE"])
        self.assertEqual(int(result["request_results"].iloc[0]["unfilled_quantity"]), 0)


if __name__ == "__main__":
    unittest.main()
