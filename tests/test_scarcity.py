import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))

from resource_dispatch.scarcity import calculate_local_scarcity


class LocalScarcityTests(unittest.TestCase):
    def test_score_is_shortage_fraction_by_district_and_resource_type(self):
        requests = pd.DataFrame([
            {"district": "Ratnapura", "requested_resource_type": "AMB", "requested_quantity": 3},
            {"district": "Ratnapura", "requested_resource_type": "AMB", "requested_quantity": 2},
            {"district": "Badulla", "requested_resource_type": "AMB", "requested_quantity": 2},
        ])
        inventory = pd.DataFrame([
            {"district": "Ratnapura", "resource_type": "AMB", "available_count": 2},
            {"district": "Ratnapura", "resource_type": "AMB", "available_count": 1},
            {"district": "Badulla", "resource_type": "AMB", "available_count": 5},
        ])

        result = calculate_local_scarcity(requests, inventory).set_index("district")

        self.assertEqual(int(result.loc["Ratnapura", "local_demand_quantity"]), 5)
        self.assertEqual(int(result.loc["Ratnapura", "local_available_quantity"]), 3)
        self.assertEqual(int(result.loc["Ratnapura", "local_shortage_quantity"]), 2)
        self.assertAlmostEqual(result.loc["Ratnapura", "local_scarcity_score"], 0.4)
        self.assertEqual(int(result.loc["Badulla", "local_shortage_quantity"]), 0)
        self.assertEqual(result.loc["Badulla", "local_scarcity_score"], 0)

    def test_missing_local_supply_has_maximum_scarcity_score(self):
        requests = pd.DataFrame([
            {"district": "Kegalle", "requested_resource_type": "RT", "requested_quantity": 4},
        ])
        inventory = pd.DataFrame([
            {"district": "Ratnapura", "resource_type": "RT", "available_count": 3},
        ])

        result = calculate_local_scarcity(requests, inventory).iloc[0]

        self.assertEqual(result["local_available_quantity"], 0)
        self.assertEqual(result["local_shortage_quantity"], 4)
        self.assertEqual(result["local_scarcity_score"], 1)

    def test_keys_are_case_and_whitespace_insensitive(self):
        requests = pd.DataFrame([
            {"district": " Ratnapura ", "requested_resource_type": "amb", "requested_quantity": 4},
        ])
        inventory = pd.DataFrame([
            {"district": "ratnapura", "resource_type": "AMB", "available_count": 1},
        ])

        result = calculate_local_scarcity(requests, inventory).iloc[0]

        self.assertEqual(result["local_available_quantity"], 1)
        self.assertAlmostEqual(result["local_scarcity_score"], 0.75)


if __name__ == "__main__":
    unittest.main()
