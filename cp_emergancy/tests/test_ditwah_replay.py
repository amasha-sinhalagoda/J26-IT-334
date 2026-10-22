import unittest

import pandas as pd

from scripts.prepare_ditwah_replay import build_ditwah_replay


def replay_tables():
    return {
        "events": pd.DataFrame([{
            "event_id": "EV-NWE-DIT",
            "scenario_id": "SC-NWE-DIT",
            "district": "Nuwara Eliya",
            "started_at": pd.Timestamp("2025-11-27"),
            "ended_at": pd.Timestamp("2025-11-28 23:59"),
        }]),
        "incident_points": pd.DataFrame([
            {
                "event_id": "EV-NWE-HIST",
                "district": "Nuwara Eliya",
                "occurred_at": pd.Timestamp("2025-11-25"),
                "incident_record_id": "historical-context",
            },
            {
                "event_id": "EV-OTHER",
                "district": "Badulla",
                "occurred_at": pd.Timestamp("2025-11-26"),
                "incident_record_id": "other-district",
            },
        ]),
        "hazard_polygons": pd.DataFrame(columns=[
            "event_id", "scenario_id", "hazard_id",
        ]),
        "road_closures": pd.DataFrame(columns=["event_id", "closure_id"]),
        "evacuation_origins": pd.DataFrame([{
            "origin_id": "ditwah-hr-1",
            "scenario_id": "SC-NWE-DIT",
            "district": "Nuwara Eliya",
            "origin_type": "HR",
            "affected_people": None,
            "source_type": "official",
            "is_synthetic": False,
        }]),
    }


class DitwahReplayTests(unittest.TestCase):
    def test_bundle_keeps_context_separate_and_reports_missing_ground_truth(self):
        bundle = build_ditwah_replay(replay_tables())

        self.assertFalse(
            bundle["readiness"]["ready_for_hazard_route_validation"]
        )
        self.assertEqual(
            ["no_event_linked_hazard_footprints",
             "affected_people_missing_for_1_origins"],
            bundle["readiness"]["blockers"],
        )
        self.assertEqual(
            [],
            bundle["inputs"]["event_linked_incidents"],
        )
        self.assertEqual(
            ["historical-context"],
            [
                row["incident_record_id"]
                for row in bundle["inputs"]["near_window_context_incidents"]
            ],
        )
        self.assertFalse(
            bundle["readiness"]["context_incidents_are_ground_truth"]
        )
        self.assertFalse(
            bundle["readiness"]["hazards_or_closures_inferred_from_other_events"]
        )

    def test_rejects_duplicate_origin_ids(self):
        tables = replay_tables()
        tables["evacuation_origins"] = pd.concat(
            [tables["evacuation_origins"], tables["evacuation_origins"]],
            ignore_index=True,
        )
        with self.assertRaisesRegex(ValueError, "duplicate origin IDs"):
            build_ditwah_replay(tables)

    def test_rejects_origins_from_another_district(self):
        tables = replay_tables()
        tables["evacuation_origins"].loc[0, "district"] = "Badulla"
        with self.assertRaisesRegex(ValueError, "another district"):
            build_ditwah_replay(tables)


if __name__ == "__main__":
    unittest.main()
