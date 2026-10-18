import argparse
from datetime import timedelta
import json
from pathlib import Path
import sys

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
INPUT_DIR = PROJECT_DIR / "processed_data" / "dual_route"
OUTPUT_FILE = INPUT_DIR / "scenarios" / "ditwah_replay.json"
EVENT_ID = "EV-NWE-DIT"
SCENARIO_ID = "SC-NWE-DIT"
INCIDENT_CONTEXT_DAYS = 7
INPUT_FILES = {
    "events": "events.csv",
    "incident_points": "incident_points.csv",
    "hazard_polygons": "hazard_polygons.csv",
    "road_closures": "road_closures.csv",
    "evacuation_origins": "evacuation_origins.csv",
}


def _load_inputs(input_dir):
    input_dir = Path(input_dir)
    tables = {
        name: pd.read_csv(input_dir / filename)
        for name, filename in INPUT_FILES.items()
    }
    for column in ("started_at", "ended_at"):
        tables["events"][column] = pd.to_datetime(
            tables["events"][column], errors="raise"
        )
    tables["incident_points"]["occurred_at"] = pd.to_datetime(
        tables["incident_points"]["occurred_at"], errors="raise"
    )
    return tables


def _records(frame):
    return json.loads(frame.to_json(orient="records", date_format="iso"))


def build_ditwah_replay(tables):
    required = {
        "events": {"event_id", "scenario_id", "district", "started_at", "ended_at"},
        "incident_points": {"event_id", "district", "occurred_at"},
        "hazard_polygons": {"event_id", "scenario_id"},
        "road_closures": {"event_id"},
        "evacuation_origins": {
            "origin_id", "scenario_id", "district", "origin_type",
            "affected_people", "source_type", "is_synthetic",
        },
    }
    for name, columns in required.items():
        missing = sorted(columns - set(tables[name].columns))
        if missing:
            raise ValueError(
                "{} is missing required columns: {}".format(name, missing)
            )

    event_rows = tables["events"][
        tables["events"]["event_id"].eq(EVENT_ID)
        & tables["events"]["scenario_id"].eq(SCENARIO_ID)
    ]
    if len(event_rows) != 1:
        raise ValueError(
            "Expected exactly one {} event for {}".format(EVENT_ID, SCENARIO_ID)
        )
    event = event_rows.iloc[0]
    district_key = str(event["district"]).strip().casefold()
    started_at = pd.Timestamp(event["started_at"])
    ended_at = pd.Timestamp(event["ended_at"])
    if pd.isna(started_at) or pd.isna(ended_at) or started_at > ended_at:
        raise ValueError("Ditwah event has an invalid event window")

    origins = tables["evacuation_origins"][
        tables["evacuation_origins"]["scenario_id"].eq(SCENARIO_ID)
    ].copy()
    if origins.empty:
        raise ValueError("Ditwah scenario has no evacuation origins")
    if origins["origin_id"].isna().any() or origins["origin_id"].duplicated().any():
        raise ValueError("Ditwah origins contain blank or duplicate origin IDs")
    wrong_district = origins[
        origins["district"].astype("string").str.strip().str.casefold()
        != district_key
    ]
    if not wrong_district.empty:
        raise ValueError("Ditwah scenario origins include another district")

    event_incidents = tables["incident_points"][
        tables["incident_points"]["event_id"].eq(EVENT_ID)
    ].copy()
    context_start = started_at - timedelta(days=INCIDENT_CONTEXT_DAYS)
    incident_district_matches = (
        tables["incident_points"]["district"]
        .astype("string")
        .str.strip()
        .str.casefold()
        .eq(district_key)
    )
    context_incidents = tables["incident_points"][
        incident_district_matches
        & tables["incident_points"]["occurred_at"].ge(context_start)
        & tables["incident_points"]["occurred_at"].le(ended_at)
        & ~tables["incident_points"]["event_id"].eq(EVENT_ID)
    ].copy()
    hazards = tables["hazard_polygons"][
        tables["hazard_polygons"]["event_id"].eq(EVENT_ID)
        | tables["hazard_polygons"]["scenario_id"].eq(SCENARIO_ID)
    ].copy()
    closures = tables["road_closures"][
        tables["road_closures"]["event_id"].eq(EVENT_ID)
    ].copy()

    unknown_demand_count = int(origins["affected_people"].isna().sum())
    blockers = []
    if hazards.empty:
        blockers.append("no_event_linked_hazard_footprints")
    if unknown_demand_count:
        blockers.append("affected_people_missing_for_{}_origins".format(
            unknown_demand_count
        ))
    warnings = []
    if not event_incidents.empty:
        warnings.append("event_linked_incidents_are_proxy_evidence")
    if closures.empty:
        warnings.append("no_event_linked_road_closures")

    return {
        "schema_version": 1,
        "scenario": _records(event_rows)[0],
        "ground_truth_status": (
            "proxy_only; NBRI slope failures near roads are not confirmed road closures"
        ),
        "incident_context_window_days_before_event": INCIDENT_CONTEXT_DAYS,
        "inputs": {
            "evacuation_origins": _records(origins),
            "event_linked_incidents": _records(event_incidents),
            "near_window_context_incidents": _records(context_incidents),
            "event_linked_hazard_footprints": _records(hazards),
            "event_linked_road_closures": _records(closures),
        },
        "readiness": {
            "ready_for_hazard_route_validation": not blockers,
            "blockers": blockers,
            "warnings": warnings,
            "counts": {
                "origins": int(len(origins)),
                "HR_origins": int(origins["origin_type"].eq("HR").sum()),
                "unknown_affected_people": unknown_demand_count,
                "event_linked_incidents": int(len(event_incidents)),
                "near_window_context_incidents": int(len(context_incidents)),
                "event_linked_hazard_footprints": int(len(hazards)),
                "event_linked_road_closures": int(len(closures)),
            },
            "context_incidents_are_ground_truth": False,
            "hazards_or_closures_inferred_from_other_events": False,
        },
        "provenance_policy": (
            "Only explicit event_id/scenario_id links are treated as scenario "
            "evidence. Nearby incidents are context only; features from other "
            "events are not copied into Ditwah."
        ),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Prepare a provenance-preserving Ditwah replay input bundle."
    )
    parser.add_argument(
        "--input-dir",
        type=Path,
        default=INPUT_DIR,
        help="Directory containing the preprocessed dual-route CSV files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT_FILE,
        help="Output JSON bundle path.",
    )
    args = parser.parse_args()
    try:
        bundle = build_ditwah_replay(_load_inputs(args.input_dir))
    except (OSError, ValueError, KeyError, pd.errors.ParserError) as exc:
        print("Ditwah replay preparation failed: {}".format(exc), file=sys.stderr)
        return 1

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(bundle, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    print("Ditwah replay bundle written to {}".format(args.output))
    print(json.dumps(bundle["readiness"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
