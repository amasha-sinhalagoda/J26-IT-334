import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch.baselines import solve_greedy_allocation


def request(alert_id, priority, scarcity, quantity=1, rank=1):
    return {
        "alert_id": alert_id,
        "requested_resource_type": "AMB",
        "requested_quantity": quantity,
        "priority_score": priority,
        "priority_rank": rank,
        "local_scarcity_score": scarcity,
    }


def candidate(alert_id, resource_id, distance, priority, scarcity, quantity=1):
    return {
        "alert_id": alert_id,
        "requested_resource_type": "AMB",
        "requested_quantity": quantity,
        "priority_score": priority,
        "local_scarcity_score": scarcity,
        "resource_id": resource_id,
        "candidate_resource_type": "AMB",
        "available_quantity": 1,
        "straight_line_distance_km": distance,
    }


class GreedyBaselineTests(unittest.TestCase):
    def test_higher_dispatch_score_gets_limited_supply_first(self):
        requests = pd.DataFrame([
            request("LOWER_SCORE", 0.9, 0.0, rank=1),
            request("HIGHER_SCORE", 0.7, 1.0, rank=2),
        ])
        supply = pd.DataFrame([
            {"resource_id": "R1", "resource_type": "AMB", "available_count": 1},
        ])
        candidates = pd.DataFrame([
            candidate("LOWER_SCORE", "R1", 1, 0.9, 0.0),
            candidate("HIGHER_SCORE", "R1", 10, 0.7, 1.0),
        ])

        result = solve_greedy_allocation(requests, supply, candidates)
        allocation = result["request_results"].set_index("alert_id")

        self.assertEqual(int(allocation.loc["LOWER_SCORE", "allocated_quantity"]), 0)
        self.assertEqual(int(allocation.loc["HIGHER_SCORE", "allocated_quantity"]), 1)

    def test_nearest_resource_is_used_when_request_priority_is_equal(self):
        requests = pd.DataFrame([request("A", 0.8, 0.5)])
        supply = pd.DataFrame([
            {"resource_id": "NEAR", "resource_type": "AMB", "available_count": 1},
            {"resource_id": "FAR", "resource_type": "AMB", "available_count": 1},
        ])
        candidates = pd.DataFrame([
            candidate("A", "FAR", 20, 0.8, 0.5),
            candidate("A", "NEAR", 2, 0.8, 0.5),
        ])

        result = solve_greedy_allocation(requests, supply, candidates)

        self.assertEqual(result["allocations"]["resource_id"].tolist(), ["NEAR"])

    def test_shared_resource_capacity_is_not_reused(self):
        requests = pd.DataFrame([
            request("A", 0.8, 0.5, rank=1),
            request("B", 0.7, 0.5, rank=2),
        ])
        supply = pd.DataFrame([
            {"resource_id": "R1", "resource_type": "AMB", "available_count": 1},
        ])
        candidates = pd.DataFrame([
            candidate("A", "R1", 1, 0.8, 0.5),
            candidate("B", "R1", 2, 0.7, 0.5),
        ])

        result = solve_greedy_allocation(requests, supply, candidates)

        self.assertEqual(int(result["allocations"]["allocated_quantity"].sum()), 1)
        self.assertEqual(
            int(result["resource_results"].iloc[0]["remaining_quantity"]), 0
        )
        self.assertEqual(
            int(result["request_results"]["unfilled_quantity"].sum()), 1
        )

    def test_demand_without_candidates_is_reported_unfilled(self):
        requests = pd.DataFrame([request("A", 0.8, 0.5)])
        supply = pd.DataFrame(columns=[
            "resource_id", "resource_type", "available_count",
        ])
        candidates = pd.DataFrame(columns=[
            "alert_id", "requested_resource_type", "requested_quantity",
            "priority_score", "local_scarcity_score", "resource_id",
            "candidate_resource_type", "available_quantity",
            "straight_line_distance_km",
        ])

        result = solve_greedy_allocation(requests, supply, candidates)

        self.assertEqual(int(result["request_results"].iloc[0]["allocated_quantity"]), 0)
        self.assertEqual(int(result["request_results"].iloc[0]["unfilled_quantity"]), 1)

    def test_invalid_candidate_distance_is_rejected(self):
        requests = pd.DataFrame([request("A", 0.8, 0.5)])
        supply = pd.DataFrame([
            {"resource_id": "R1", "resource_type": "AMB", "available_count": 1},
        ])
        candidates = pd.DataFrame([
            candidate("A", "R1", float("inf"), 0.8, 0.5),
        ])

        with self.assertRaisesRegex(ValueError, "distances must be finite"):
            solve_greedy_allocation(requests, supply, candidates)


if __name__ == "__main__":
    unittest.main()
