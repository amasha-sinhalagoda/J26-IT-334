import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys
from time import perf_counter

from sqlalchemy import create_engine

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from scripts.prepare_ditwah_replay import INPUT_DIR
from scripts.route_evacuation import database_url, plan_evacuation


REPLAY_FILE = INPUT_DIR / "scenarios" / "ditwah_replay.json"
ROUTE_OUTPUT_FILE = INPUT_DIR / "routes" / "ditwah_evacuation.json"
EVALUATION_OUTPUT_FILE = INPUT_DIR / "scenarios" / "ditwah_evaluation.json"
SCENARIO_ID = "SC-NWE-DIT"
LATENCY_TARGET_SECONDS = 5.0


def build_evaluation(replay_bundle, route_plan, elapsed_seconds):
    if route_plan["scenario"]["scenario_id"] != SCENARIO_ID:
        raise ValueError("Route plan is not for {}".format(SCENARIO_ID))
    if replay_bundle["scenario"]["scenario_id"] != SCENARIO_ID:
        raise ValueError("Replay bundle is not for {}".format(SCENARIO_ID))
    if (
        not isinstance(elapsed_seconds, (int, float))
        or not math.isfinite(elapsed_seconds)
        or elapsed_seconds < 0
    ):
        raise ValueError("elapsed_seconds must be a non-negative number")

    readiness = replay_bundle["readiness"]
    counts = readiness["counts"]
    origins = route_plan["origins"]
    route_count = sum(len(origin.get("assignments", [])) for origin in origins)
    route_edge_count = sum(
        len(assignment["route"]["edges"])
        for origin in origins
        for assignment in origin.get("assignments", [])
    )
    statuses = Counter(origin.get("status") for origin in origins)
    reasons = Counter(origin.get("reason") for origin in origins)
    route_evaluation_ready = (
        readiness["ready_for_hazard_route_validation"]
        and counts["event_linked_hazard_footprints"] > 0
        and counts["unknown_affected_people"] == 0
        and route_count > 0
    )

    if route_evaluation_ready:
        safety_metric = {
            "status": "requires_edge_level_validation",
            "routes_emitted": route_count,
            "zero_hard_blocked_route_share": None,
            "reason": "Edge-level closure/flood/landslide validation is required.",
        }
    else:
        safety_metric = {
            "status": "not_evaluable",
            "routes_emitted": route_count,
            "zero_hard_blocked_route_share": None,
            "reason": (
                "No event-linked hard-hazard ground truth and no complete "
                "known-demand route set; an empty route set cannot establish safety."
            ),
        }

    baseline = {
        "status": "not_evaluable",
        "baseline_routes_crossing_confirmed_blocked_edges_share": None,
        "detour_ratio": None,
        "reason": (
            "The scenario has no event-linked blocked-edge evidence and emitted "
            "no evacuation routes for comparison."
        ),
    }
    sensitivity = {
        "status": "not_evaluable",
        "buffer_size_variants": [],
        "soft_penalty_variants": [],
        "reason": (
            "Route comparisons require event-linked hazard evidence and known "
            "origin demand; no thresholds or weights are calibrated from this replay."
        ),
    }
    return {
        "schema_version": 1,
        "evaluated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scenario_id": SCENARIO_ID,
        "evaluation_status": (
            "not_evaluable" if not route_evaluation_ready else "partial"
        ),
        "input_readiness": readiness,
        "request_latency": {
            "status": "measured_short_circuit",
            "elapsed_seconds": round(float(elapsed_seconds), 6),
            "target_seconds": LATENCY_TARGET_SECONDS,
            "under_target": elapsed_seconds < LATENCY_TARGET_SECONDS,
            "full_route_search_performed": route_count > 0,
            "interpretation": (
                "This measures the planner response for the supplied input. "
                "Because all origins have unknown affected_people, the planner "
                "does not build the graph or search for paths; it is not a full "
                "routing-latency benchmark."
            ),
        },
        "route_safety": safety_metric,
        "baseline_comparison": baseline,
        "sensitivity_analysis": sensitivity,
        "planner_outcome": {
            "status": route_plan["status"],
            "origin_count": len(origins),
            "origin_status_counts": dict(sorted(statuses.items())),
            "origin_reason_counts": dict(sorted(reasons.items())),
            "known_people": route_plan["demand"]["known_people"],
            "unknown_demand_origin_count": (
                route_plan["demand"]["unknown_demand_origin_count"]
            ),
            "served_people": route_plan["demand"]["served_people"],
            "unserved_known_people": (
                route_plan["demand"]["unserved_known_people"]
            ),
            "route_count": route_count,
            "route_edge_count": route_edge_count,
        },
        "ground_truth_constraints": {
            "event_linked_incidents": counts["event_linked_incidents"],
            "near_window_context_incidents": counts[
                "near_window_context_incidents"
            ],
            "event_linked_hazard_footprints": counts[
                "event_linked_hazard_footprints"
            ],
            "event_linked_road_closures": counts["event_linked_road_closures"],
            "context_incidents_are_confirmed_closures": False,
            "proxy_ground_truth_only": True,
        },
    }


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Run and report the Ditwah evacuation-plan evaluation without "
            "treating incomplete data as successful routing."
        )
    )
    parser.add_argument("--replay", type=Path, default=REPLAY_FILE)
    parser.add_argument("--routes-output", type=Path, default=ROUTE_OUTPUT_FILE)
    parser.add_argument("--output", type=Path, default=EVALUATION_OUTPUT_FILE)
    args = parser.parse_args()

    try:
        replay_bundle = json.loads(args.replay.read_text(encoding="utf-8"))
        engine = create_engine(database_url(), pool_pre_ping=True)
        try:
            started = perf_counter()
            route_plan = plan_evacuation(engine, SCENARIO_ID)
            elapsed_seconds = perf_counter() - started
        finally:
            engine.dispose()
        evaluation = build_evaluation(
            replay_bundle,
            route_plan,
            elapsed_seconds,
        )
        args.routes_output.parent.mkdir(parents=True, exist_ok=True)
        args.routes_output.write_text(
            json.dumps(route_plan, indent=2, sort_keys=True, default=str) + "\n",
            encoding="utf-8",
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(evaluation, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Ditwah replay evaluation failed: {}".format(exc), file=sys.stderr)
        return 1

    print("Ditwah route plan written to {}".format(args.routes_output))
    print("Ditwah evaluation written to {}".format(args.output))
    print(json.dumps({
        "evaluation_status": evaluation["evaluation_status"],
        "request_latency": evaluation["request_latency"],
        "route_safety_status": evaluation["route_safety"]["status"],
        "origin_status_counts": (
            evaluation["planner_outcome"]["origin_status_counts"]
        ),
        "route_count": evaluation["planner_outcome"]["route_count"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
