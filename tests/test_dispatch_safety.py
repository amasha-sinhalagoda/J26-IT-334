import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "src"))
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

from resource_dispatch.dispatch_safety import (
    inventory_after_reservations,
    load_reservations,
    reserve_dispatch_plan,
)
from run_allocation_solver import _prepare_pending_inputs


class DispatchReservationTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.ledger_path = Path(self.temp_dir.name) / "reservations.csv"
        self.inventory = pd.DataFrame([
            {
                "resource_id": "R1",
                "resource_type": "AMB",
                "district": "Ratnapura",
                "available_count": 3,
            },
            {
                "resource_id": "R2",
                "resource_type": "AMB",
                "district": "Badulla",
                "available_count": 2,
            },
        ])
        self.requests = pd.DataFrame([
            {
                "alert_id": "A",
                "requested_resource_type": "AMB",
                "requested_quantity": 4,
                "district": "Ratnapura",
                "priority_score": 0.8,
                "priority_rank": 1,
            },
        ])
        self.candidates = pd.DataFrame([
            {
                "alert_id": "A",
                "requested_resource_type": "AMB",
                "requested_quantity": 4,
                "priority_score": 0.8,
                "priority_rank": 1,
                "local_scarcity_score": 0.25,
                "resource_id": "R1",
                "available_quantity": 3,
                "straight_line_distance_km": 1.0,
            },
            {
                "alert_id": "A",
                "requested_resource_type": "AMB",
                "requested_quantity": 4,
                "priority_score": 0.8,
                "priority_rank": 1,
                "local_scarcity_score": 0.25,
                "resource_id": "R2",
                "available_quantity": 2,
                "straight_line_distance_km": 5.0,
            },
        ])

    def tearDown(self):
        self.temp_dir.cleanup()

    def plan(self, resource_id, quantity, request_quantity=4):
        return pd.DataFrame([{
            "alert_id": "A",
            "resource_id": resource_id,
            "requested_resource_type": "AMB",
            "requested_quantity": request_quantity,
            "allocated_quantity": quantity,
        }])

    def test_reservation_persists_and_reduces_future_inventory_and_demand(self):
        first_plan = self.plan("R1", 2)
        reservations = reserve_dispatch_plan(
            first_plan, self.requests, self.inventory, self.ledger_path
        )

        self.assertTrue(self.ledger_path.exists())
        self.assertEqual(int(reservations["reserved_quantity"].sum()), 2)
        persisted = load_reservations(self.ledger_path)
        effective_inventory = inventory_after_reservations(
            self.inventory, persisted
        )
        self.assertEqual(
            int(effective_inventory.set_index("resource_id").loc["R1", "available_count"]),
            1,
        )

        pending_requests, supply, candidates = _prepare_pending_inputs(
            self.requests, self.candidates, self.inventory, persisted
        )
        self.assertEqual(int(pending_requests.iloc[0]["requested_quantity"]), 2)
        self.assertEqual(
            int(supply.set_index("resource_id").loc["R1", "available_count"]), 1
        )
        self.assertEqual(
            int(candidates.set_index("resource_id").loc["R1", "available_quantity"]),
            1,
        )

    def test_over_reservation_is_rejected_without_changing_ledger(self):
        reserve_dispatch_plan(
            self.plan("R1", 2), self.requests, self.inventory, self.ledger_path
        )
        before = self.ledger_path.read_bytes()

        with self.assertRaisesRegex(ValueError, "exceeds current available"):
            reserve_dispatch_plan(
                self.plan("R1", 2), self.requests, self.inventory, self.ledger_path
            )

        self.assertEqual(self.ledger_path.read_bytes(), before)
        self.assertEqual(len(load_reservations(self.ledger_path)), 1)

    def test_reservations_cannot_exceed_total_alert_request(self):
        requests = self.requests.copy()
        requests.loc[0, "requested_quantity"] = 3
        plan = pd.concat(
            [self.plan("R1", 2, request_quantity=3), self.plan("R2", 2, request_quantity=3)],
            ignore_index=True,
        )

        with self.assertRaisesRegex(ValueError, "exceeds a request quantity"):
            reserve_dispatch_plan(plan, requests, self.inventory, self.ledger_path)

        self.assertFalse(self.ledger_path.exists())

    def test_preview_inputs_do_not_create_or_modify_reservation_ledger(self):
        pending_requests, supply, candidates = _prepare_pending_inputs(
            self.requests,
            self.candidates,
            self.inventory,
            load_reservations(self.ledger_path),
        )

        self.assertEqual(len(pending_requests), 1)
        self.assertEqual(int(pending_requests.iloc[0]["requested_quantity"]), 4)
        self.assertEqual(int(supply["available_count"].sum()), 5)
        self.assertEqual(len(candidates), 2)
        self.assertFalse(self.ledger_path.exists())


if __name__ == "__main__":
    unittest.main()
