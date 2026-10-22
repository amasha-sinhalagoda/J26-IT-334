import unittest

from scripts.evaluate_ditwah_replay import build_evaluation


def evaluation_inputs():
    replay_bundle = {
        "scenario": {"scenario_id": "SC-NWE-DIT"},
        "readiness": {
            "ready_for_hazard_route_validation": False,
            "blockers": [
                "no_event_linked_hazard_footprints",
                "affected_people_missing_for_2_origins",
            ],
            "warnings": ["no_event_linked_road_closures"],
            "counts": {
                "event_linked_incidents": 0,
                "near_window_context_incidents": 1,
                "event_linked_hazard_footprints": 0,
                "event_linked_road_closures": 0,
                "unknown_affected_people": 2,
            },
            "context_incidents_are_ground_truth": False,
            "hazards_or_closures_inferred_from_other_events": False,
        },
    }
    route_plan = {
        "scenario": {"scenario_id": "SC-NWE-DIT"},
        "status": "infeasible",
        "demand": {
            "known_people": 0,
            "unknown_demand_origin_count": 2,
            "served_people": 0,
            "unserved_known_people": 0,
        },
        "origins": [
            {
                "status": "infeasible",
                "reason": "affected_people_unknown",
                "assignments": [],
            },
            {
                "status": "infeasible",
                "reason": "affected_people_unknown",
                "assignments": [],
            },
        ],
    }
    return replay_bundle, route_plan


class DitwahEvaluationTests(unittest.TestCase):
    def test_missing_ground_truth_and_demand_do_not_score_empty_routes_as_safe(self):
        replay_bundle, route_plan = evaluation_inputs()
        result = build_evaluation(replay_bundle, route_plan, 1.25)

        self.assertEqual("not_evaluable", result["evaluation_status"])
        self.assertEqual("not_evaluable", result["route_safety"]["status"])
        self.assertIsNone(
            result["route_safety"]["zero_hard_blocked_route_share"]
        )
        self.assertFalse(
            result["request_latency"]["full_route_search_performed"]
        )
        self.assertEqual(
            {"infeasible": 2},
            result["planner_outcome"]["origin_status_counts"],
        )
        self.assertEqual(
            {"affected_people_unknown": 2},
            result["planner_outcome"]["origin_reason_counts"],
        )
        self.assertEqual("not_evaluable", result["baseline_comparison"]["status"])
        self.assertEqual("not_evaluable", result["sensitivity_analysis"]["status"])

    def test_rejects_a_route_plan_for_another_scenario(self):
        replay_bundle, route_plan = evaluation_inputs()
        route_plan["scenario"]["scenario_id"] = "SC-RTN-F1"
        with self.assertRaisesRegex(ValueError, "not for SC-NWE-DIT"):
            build_evaluation(replay_bundle, route_plan, 1.0)

    def test_rejects_invalid_latency(self):
        replay_bundle, route_plan = evaluation_inputs()
        with self.assertRaisesRegex(ValueError, "non-negative"):
            build_evaluation(replay_bundle, route_plan, -1.0)


if __name__ == "__main__":
    unittest.main()
