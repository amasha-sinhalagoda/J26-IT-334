import argparse
import json
from pathlib import Path
import re
import sys

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
RDA_WORKBOOK = PROJECT_DIR / "RDA_National_Road_Network.xlsx"
ROAD_GRAPH_DIR = PROJECT_DIR / "processed_data" / "dual_route" / "road_graph"
INPUT_GPKG = ROAD_GRAPH_DIR / "five_districts.gpkg"
INPUT_GRAPHML = ROAD_GRAPH_DIR / "five_districts.graphml"
OUTPUT_CROSSWALK = ROAD_GRAPH_DIR / "rda_crosswalk.csv"
OUTPUT_GPKG = ROAD_GRAPH_DIR / "five_districts_rda.gpkg"
OUTPUT_GRAPHML = ROAD_GRAPH_DIR / "five_districts_rda.graphml"

RDA_REQUIRED_COLUMNS = (
    "Route Number",
    "Road Class",
    "Sub-class",
    "Road Name",
    "Road Length (km)",
)
DIRECT_PREFIXES = {"AA", "AB", "AC", "B", "E"}
RDA_EDGE_COLUMNS = {
    "rda_code": "string",
    "rda_class": "string",
    "rda_subclass": "string",
    "rda_road_name": "string",
    "rda_road_length_km": "float64",
    "rda_match_status": "string",
    "rda_candidate_codes": "string",
}


def normalize_route_code(value):
    if value is None or pd.isna(value):
        return None
    compact = re.sub(r"\s+", "", str(value).upper())
    match = re.fullmatch(r"([A-Z]+)0*(\d+)", compact)
    if match is None:
        return compact
    prefix, digits = match.groups()
    return "{}{}".format(prefix, int(digits))


def prepare_rda_records(rda_frame):
    missing = sorted(set(RDA_REQUIRED_COLUMNS) - set(rda_frame.columns))
    if missing:
        raise ValueError("RDA workbook is missing columns: {}".format(missing))

    records = rda_frame[list(RDA_REQUIRED_COLUMNS)].copy()
    records.columns = [
        "rda_code",
        "rda_class",
        "rda_subclass",
        "rda_road_name",
        "rda_road_length_km",
    ]
    records["rda_code"] = records["rda_code"].astype("string").str.strip().str.upper()
    records = records.loc[
        records["rda_code"].notna() & records["rda_code"].ne("")
    ].copy()
    records["normalized_code"] = records["rda_code"].map(normalize_route_code)

    duplicated = records["normalized_code"].duplicated(keep=False)
    if duplicated.any():
        codes = records.loc[duplicated, "rda_code"].tolist()
        raise ValueError(
            "RDA route codes collide after normalization: {}".format(codes[:20])
        )
    return records


def _a_route_candidates(normalized_ref, records_by_code):
    match = re.fullmatch(r"A(\d+)", normalized_ref or "")
    if match is None:
        return []
    number = match.group(1)
    candidate_codes = []
    for prefix in ("AA", "AB", "AC"):
        record = records_by_code.get(normalize_route_code(prefix + number))
        if record is not None:
            candidate_codes.append(record["rda_code"])
    return sorted(candidate_codes)


def build_crosswalk(osm_refs, rda_frame, edge_counts=None):
    records = prepare_rda_records(rda_frame)
    records_by_code = {
        record["normalized_code"]: record
        for record in records.to_dict("records")
    }
    edge_counts = edge_counts or {}
    rows = []
    seen = set()

    for value in osm_refs:
        if value is None or pd.isna(value):
            continue
        osm_ref = str(value).strip()
        if not osm_ref or osm_ref in seen:
            continue
        seen.add(osm_ref)
        normalized_ref = normalize_route_code(osm_ref)
        prefix_match = re.match(r"^[A-Z]+", normalized_ref or "")
        prefix = prefix_match.group(0) if prefix_match else ""
        record = records_by_code.get(normalized_ref)
        candidates = []

        if record is not None and prefix in DIRECT_PREFIXES:
            status = "matched_normalized_code"
        elif prefix == "A":
            candidates = _a_route_candidates(normalized_ref, records_by_code)
            status = "ambiguous_a_subclass" if candidates else "unmatched"
            record = None
        else:
            status = "unmatched"
            record = None

        row = {
            "osm_ref": osm_ref,
            "normalized_osm_ref": normalized_ref,
            "edge_count": int(edge_counts.get(osm_ref, 0)),
            "rda_code": record["rda_code"] if record is not None else None,
            "rda_class": record["rda_class"] if record is not None else None,
            "rda_subclass": record["rda_subclass"] if record is not None else None,
            "rda_road_name": record["rda_road_name"] if record is not None else None,
            "rda_road_length_km": (
                record["rda_road_length_km"] if record is not None else None
            ),
            "match_status": status,
            "candidate_codes": json.dumps(candidates, ensure_ascii=False),
            "match_basis": (
                "Normalized route code; leading zeroes removed"
                if record is not None
                else (
                    "A-number is ambiguous across RDA AA/AB/AC subclasses"
                    if candidates
                    else "No unique normalized RDA route-code match"
                )
            ),
        }
        rows.append(row)

    return pd.DataFrame(rows).sort_values("osm_ref").reset_index(drop=True)


def _build_lookup(crosswalk):
    return {
        row["osm_ref"]: row
        for row in crosswalk.to_dict("records")
    }


def _add_edge_crosswalk_fields(edges, crosswalk):
    edges = edges.copy()
    lookup = _build_lookup(crosswalk)

    for column in RDA_EDGE_COLUMNS:
        if column not in edges:
            edges[column] = None

    for index, osm_ref in edges["ref"].items():
        if pd.isna(osm_ref) or not str(osm_ref).strip():
            edges.at[index, "rda_match_status"] = "missing_osm_ref"
            edges.at[index, "rda_candidate_codes"] = "[]"
            continue
        row = lookup.get(str(osm_ref).strip())
        if row is None:
            edges.at[index, "rda_match_status"] = "unmatched"
            edges.at[index, "rda_candidate_codes"] = "[]"
            continue
        for field in RDA_EDGE_COLUMNS:
            crosswalk_field = (
                "match_status" if field == "rda_match_status"
                else "candidate_codes" if field == "rda_candidate_codes"
                else field
            )
            edges.at[index, field] = row[crosswalk_field]

    for column, dtype in RDA_EDGE_COLUMNS.items():
        edges[column] = edges[column].astype(dtype)
    return edges


def _write_crosswalk(crosswalk, output_path=OUTPUT_CROSSWALK):
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    crosswalk.to_csv(output_path, index=False)
    return output_path


def _write_rda_geopackage(edges, gpkg_path, output_path=OUTPUT_GPKG):
    import geopandas as gpd
    import pyogrio

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nodes = gpd.read_file(gpkg_path, layer="road_nodes")
    boundaries = gpd.read_file(gpkg_path, layer="district_boundaries")

    if output_path.exists():
        output_path.unlink()
    edges.to_file(
        output_path, layer="road_edges", driver="GPKG", index=False
    )
    nodes.to_file(
        output_path,
        layer="road_nodes",
        driver="GPKG",
        index=False,
        mode="a",
    )
    boundaries.to_file(
        output_path,
        layer="district_boundaries",
        driver="GPKG",
        index=False,
        mode="a",
    )
    pyogrio.read_info(output_path, layer="road_edges")
    return output_path


def _write_rda_graphml(crosswalk, input_path=INPUT_GRAPHML, output_path=OUTPUT_GRAPHML):
    import osmnx as ox

    graph = ox.load_graphml(filepath=input_path)
    lookup = _build_lookup(crosswalk)
    for _, _, _, data in graph.edges(keys=True, data=True):
        osm_ref = data.get("ref")
        row = lookup.get(str(osm_ref).strip()) if osm_ref is not None else None
        if row is None:
            data["rda_code"] = ""
            data["rda_class"] = ""
            data["rda_subclass"] = ""
            data["rda_road_name"] = ""
            data["rda_match_status"] = (
                "missing_osm_ref" if osm_ref is None else "unmatched"
            )
            data["rda_candidate_codes"] = "[]"
        else:
            data["rda_code"] = row["rda_code"] or ""
            data["rda_class"] = row["rda_class"] or ""
            data["rda_subclass"] = row["rda_subclass"] or ""
            data["rda_road_name"] = row["rda_road_name"] or ""
            data["rda_match_status"] = row["match_status"]
            data["rda_candidate_codes"] = row["candidate_codes"]
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ox.io.save_graphml(graph, filepath=output_path)
    return output_path


def build_rda_crosswalk(
    rda_workbook=RDA_WORKBOOK,
    gpkg_path=INPUT_GPKG,
    graphml_path=INPUT_GRAPHML,
    output_dir=ROAD_GRAPH_DIR,
):
    import geopandas as gpd

    rda_workbook = Path(rda_workbook)
    gpkg_path = Path(gpkg_path)
    graphml_path = Path(graphml_path)
    for path in (rda_workbook, gpkg_path, graphml_path):
        if not path.is_file():
            raise FileNotFoundError("Required crosswalk input not found: {}".format(path))

    edges = gpd.read_file(gpkg_path, layer="road_edges")
    if "ref" not in edges:
        raise ValueError("Road graph edge layer is missing the OSM ref field")

    refs = edges["ref"].dropna().astype(str).str.strip()
    counts = refs[refs.ne("")].value_counts().to_dict()
    rda = pd.read_excel(rda_workbook, sheet_name="All Roads")
    crosswalk = build_crosswalk(counts.keys(), rda, counts)
    crosswalk_path = _write_crosswalk(
        crosswalk, Path(output_dir) / OUTPUT_CROSSWALK.name
    )
    edges = _add_edge_crosswalk_fields(edges, crosswalk)
    rda_gpkg = _write_rda_geopackage(
        edges,
        gpkg_path,
        Path(output_dir) / OUTPUT_GPKG.name,
    )
    rda_graphml = _write_rda_graphml(
        crosswalk,
        graphml_path,
        Path(output_dir) / OUTPUT_GRAPHML.name,
    )

    summaries = crosswalk["match_status"].value_counts().to_dict()
    edge_summaries = (
        edges["rda_match_status"].value_counts().to_dict()
    )
    report = {
        "rda_workbook": str(rda_workbook),
        "source_edges": str(gpkg_path),
        "crosswalk_csv": str(crosswalk_path),
        "annotated_geopackage": str(rda_gpkg),
        "annotated_graphml": str(rda_graphml),
        "unique_osm_refs": int(len(crosswalk)),
        "unique_ref_status_counts": summaries,
        "edge_status_counts": {
            str(key): int(value) for key, value in edge_summaries.items()
        },
        "matched_edge_count": int(
            edges["rda_match_status"].eq("matched_normalized_code").sum()
        ),
        "ambiguous_edge_count": int(
            edges["rda_match_status"].eq("ambiguous_a_subclass").sum()
        ),
        "unmatched_edge_count": int(
            edges["rda_match_status"].eq("unmatched").sum()
        ),
        "missing_ref_edge_count": int(
            edges["rda_match_status"].eq("missing_osm_ref").sum()
        ),
        "use_restriction": (
            "RDA class/subclass is a road-priority/fallback attribute only; "
            "it is not hazard evidence and must not override hard blocks."
        ),
    }
    report_path = Path(output_dir) / "rda_crosswalk_report.json"
    report_path.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return crosswalk, edges, report


def main():
    parser = argparse.ArgumentParser(description="Build the OSM-to-RDA road crosswalk.")
    parser.add_argument(
        "--rda-workbook",
        type=Path,
        default=RDA_WORKBOOK,
        help="RDA gazetted-road workbook",
    )
    parser.add_argument(
        "--gpkg",
        type=Path,
        default=INPUT_GPKG,
        help="Source road graph GeoPackage",
    )
    parser.add_argument(
        "--graphml",
        type=Path,
        default=INPUT_GRAPHML,
        help="Source road graph GraphML",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROAD_GRAPH_DIR,
        help="Crosswalk output directory",
    )
    args = parser.parse_args()
    try:
        crosswalk, edges, report = build_rda_crosswalk(
            rda_workbook=args.rda_workbook,
            gpkg_path=args.gpkg,
            graphml_path=args.graphml,
            output_dir=args.output_dir,
        )
    except (FileNotFoundError, ValueError, OSError, ImportError) as exc:
        print("RDA crosswalk build failed: {}".format(exc), file=sys.stderr)
        return 1

    print(
        "Crosswalk built for {} unique OSM refs; {} of {} edges matched directly, "
        "{} edges need A-road subclass review.".format(
            len(crosswalk),
            report["matched_edge_count"],
            len(edges),
            report["ambiguous_edge_count"],
        )
    )
    print("Crosswalk: {}".format(args.output_dir / OUTPUT_CROSSWALK.name))
    print("Report: {}".format(args.output_dir / "rda_crosswalk_report.json"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
