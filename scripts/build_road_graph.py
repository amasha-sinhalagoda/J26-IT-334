from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys


PROJECT_DIR = Path(__file__).resolve().parents[1]
SOURCE_DATA_DIR = PROJECT_DIR / "Dual route optimization" / "source_data"
PBF_PATH = SOURCE_DATA_DIR / "sri-lanka-261017.osm.pbf"
BOUNDARIES_PATH = (
    PROJECT_DIR / "processed_data" / "dual_route" / "district_boundaries.geojson"
)
OUTPUT_DIR = PROJECT_DIR / "processed_data" / "dual_route" / "road_graph"
GRAPH_PATH = OUTPUT_DIR / "five_districts.graphml"
GEOPACKAGE_PATH = OUTPUT_DIR / "five_districts.gpkg"
MANIFEST_PATH = OUTPUT_DIR / "graph_manifest.json"

TARGET_CRS = "EPSG:5234"
NETWORK_TYPE = "driving"
BOUNDARY_BUFFER_METERS = 1000

# Prototype fallback limits in km/h for edges without an OSM maxspeed tag.
# Replace with locally calibrated road speeds before operational ETA claims.
FALLBACK_SPEEDS_KMH = {
    "motorway": 80,
    "motorway_link": 50,
    "trunk": 60,
    "trunk_link": 40,
    "primary": 50,
    "primary_link": 35,
    "secondary": 40,
    "secondary_link": 30,
    "tertiary": 35,
    "tertiary_link": 25,
    "unclassified": 30,
    "residential": 25,
    "living_street": 15,
    "service": 15,
    "road": 25,
}
UNKNOWN_HIGHWAY_FALLBACK_KMH = 20

RETAINED_EDGE_COLUMNS = (
    "highway",
    "ref",
    "name",
    "bridge",
    "tunnel",
    "maxspeed",
    "length",
    "travel_time",
    "speed_kph",
    "osmid",
    "oneway",
    "oneway_osm",
    "edge_id",
)


def _require_inputs(pbf_path=PBF_PATH, boundaries_path=BOUNDARIES_PATH):
    missing = [
        str(path)
        for path in (Path(pbf_path), Path(boundaries_path))
        if not Path(path).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Road graph input file(s) not found: {}".format(", ".join(missing))
        )


def _load_target_polygon(boundaries_path=BOUNDARIES_PATH):
    import geopandas as gpd
    from pyproj import CRS

    boundaries = gpd.read_file(boundaries_path)
    if boundaries.crs is None:
        raise ValueError("District boundary GeoJSON has no declared CRS")
    if "district" not in boundaries.columns:
        raise ValueError("District boundary GeoJSON is missing its district field")

    expected = {
        "Ratnapura",
        "Kegalle",
        "Kalutara",
        "Badulla",
        "Nuwara Eliya",
    }
    found = set(boundaries["district"].dropna().astype(str))
    if found != expected:
        raise ValueError(
            "District boundaries must contain exactly {} (found {})".format(
                sorted(expected), sorted(found)
            )
        )

    target_crs = CRS.from_user_input(TARGET_CRS)
    projected = boundaries.to_crs(target_crs)
    district_union = projected.geometry.union_all()
    if district_union.is_empty or not district_union.is_valid:
        raise ValueError("Projected district union is empty or invalid")
    buffered = district_union.buffer(BOUNDARY_BUFFER_METERS)
    if buffered.is_empty or not buffered.is_valid:
        raise ValueError("Buffered district boundary is empty or invalid")
    return boundaries, projected, district_union, buffered


def _extract_graph(pbf_path, buffered_polygon):
    import geopandas as gpd
    import osmnx as ox
    from pyrosm import OSM

    buffered_wgs84 = ox.projection.project_gdf(
        gpd.GeoDataFrame(geometry=[buffered_polygon], crs=TARGET_CRS),
        to_crs="EPSG:4326",
    ).geometry.iloc[0]
    bounds = list(buffered_wgs84.bounds)
    osm = OSM(
        str(pbf_path),
        bounding_box=bounds,
        keep_metadata=False,
        workers=1,
        progress=True,
    )
    nodes, edges = osm.get_network(
        network_type=NETWORK_TYPE,
        nodes=True,
        tags_to_keep=[
            "highway",
            "ref",
            "name",
            "bridge",
            "tunnel",
            "maxspeed",
            "oneway",
            "access",
            "junction",
        ],
    )
    if nodes.empty or edges.empty:
        raise ValueError(
            "The OSM extract produced no driving roads in the target district extent"
        )
    graph = OSM.to_graph(
        nodes,
        edges,
        graph_type="networkx",
        direction="oneway",
        network_type=NETWORK_TYPE,
        retain_all=True,
        osmnx_compatible=True,
        simplify=True,
        simplify_kwargs={
            "edge_attrs_differ": [
                "highway", "ref", "name", "bridge", "tunnel", "maxspeed",
                "oneway",
            ]
        },
    )
    return ox, graph


def _normalize_oneway_tags(graph):
    one_way_values = {"yes", "true", "1", "-1"}
    for _, _, _, data in graph.edges(keys=True, data=True):
        raw_value = data.get("oneway")
        data["oneway_osm"] = raw_value
        values = raw_value if isinstance(raw_value, (list, tuple)) else [raw_value]
        data["oneway"] = any(
            str(value).strip().casefold() in one_way_values
            for value in values
            if value is not None
        )


def _edge_fingerprint(u, v, key, osmid):
    if isinstance(osmid, (list, tuple, set)):
        way_ids = sorted(str(item) for item in osmid)
    elif osmid is None:
        way_ids = []
    else:
        way_ids = [str(osmid)]
    identity = "{}|{}|{}|{}".format(u, v, key, ",".join(way_ids))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:24]
    return "osm-edge-{}".format(digest)


def _add_stable_edge_ids(graph):
    seen = set()
    for u, v, key, data in graph.edges(keys=True, data=True):
        edge_id = _edge_fingerprint(u, v, key, data.get("osmid"))
        if edge_id in seen:
            raise ValueError("Stable edge ID collision: {}".format(edge_id))
        seen.add(edge_id)
        data["edge_id"] = edge_id


def _clean_graph_attributes(graph):
    import math

    def clean(value):
        if isinstance(value, float) and not math.isfinite(value):
            return None
        if isinstance(value, dict):
            cleaned = {}
            for key, item in value.items():
                item = clean(item)
                if item is not None:
                    cleaned[str(key)] = item
            return cleaned
        if isinstance(value, (list, tuple)):
            cleaned = []
            for item in value:
                item = clean(item)
                if item is not None:
                    cleaned.append(item)
            return cleaned
        return value

    for _, data in graph.nodes(data=True):
        for key, value in list(data.items()):
            if value is None or (isinstance(value, float) and not math.isfinite(value)):
                data.pop(key, None)
            elif isinstance(value, (dict, list, tuple)):
                data[key] = clean(value)

    for _, _, _, data in graph.edges(keys=True, data=True):
        for key, value in list(data.items()):
            if value is None or (isinstance(value, float) and not math.isfinite(value)):
                data.pop(key, None)
            elif isinstance(value, (dict, list, tuple)):
                data[key] = clean(value)


def _assign_travel_times(ox, graph):
    graph = ox.routing.add_edge_speeds(
        graph,
        hwy_speeds=FALLBACK_SPEEDS_KMH,
        fallback=UNKNOWN_HIGHWAY_FALLBACK_KMH,
    )
    graph = ox.routing.add_edge_travel_times(graph)
    invalid = [
        (u, v, key)
        for u, v, key, data in graph.edges(keys=True, data=True)
        if data.get("length") is None
        or data.get("travel_time") is None
        or data["length"] <= 0
        or data["travel_time"] <= 0
    ]
    if invalid:
        raise ValueError(
            "{} graph edges have missing or non-positive length/travel_time".format(
                len(invalid)
            )
        )
    return graph


def _add_district_labels(edge_gdf, district_boundaries):
    labels = []
    geometries = district_boundaries[["district", "geometry"]]
    for geometry in edge_gdf.geometry:
        candidates = geometries.loc[geometries.intersects(geometry), "district"]
        labels.append("|".join(sorted(candidates.astype(str).unique())))
    edge_gdf["districts"] = labels
    if edge_gdf.empty:
        raise ValueError("No road edges were extracted for the target districts")
    return edge_gdf


def _write_outputs(
    ox,
    graph,
    district_boundaries,
    pbf_path=PBF_PATH,
    output_dir=OUTPUT_DIR,
):
    import geopandas as gpd
    import networkx as nx

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    graph_path = output_dir / GRAPH_PATH.name
    gpkg_path = output_dir / GEOPACKAGE_PATH.name
    manifest_path = output_dir / MANIFEST_PATH.name

    ox.io.save_graphml(graph, filepath=graph_path)
    nodes, edges = ox.convert.graph_to_gdfs(graph, nodes=True, edges=True)
    edges = edges.reset_index()
    edges = _add_district_labels(edges, district_boundaries)
    required = set(RETAINED_EDGE_COLUMNS)
    missing = sorted(required - set(edges.columns))
    if missing:
        raise ValueError("Road graph is missing required edge fields: {}".format(missing))

    selected_edges = list(dict.fromkeys(
        ["u", "v", "key", "geometry", "districts"] + list(RETAINED_EDGE_COLUMNS)
    ))
    edges = edges[selected_edges].copy()
    for column in edges.columns:
        if column == "geometry":
            continue
        edges[column] = edges[column].map(
            lambda value: (
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, (list, tuple, dict))
                else value
            )
        )

    nodes = nodes.reset_index()
    node_columns = [
        column for column in ("osmid", "x", "y", "geometry") if column in nodes
    ]
    nodes = gpd.GeoDataFrame(
        nodes[node_columns],
        geometry="geometry",
        crs=graph.graph["crs"],
    )
    node_crs = str(graph.graph["crs"])
    if node_crs != TARGET_CRS:
        raise ValueError(
            "Road graph CRS is {}, expected {}".format(node_crs, TARGET_CRS)
        )

    if gpkg_path.exists():
        gpkg_path.unlink()
    edges.to_file(gpkg_path, layer="road_edges", driver="GPKG", index=False)
    nodes.to_file(
        gpkg_path,
        layer="road_nodes",
        driver="GPKG",
        index=False,
        mode="a",
    )
    district_boundaries.to_file(
        gpkg_path,
        layer="district_boundaries",
        driver="GPKG",
        index=False,
        mode="a",
    )

    manifest = {
        "source": {
            "provider": "Geofabrik",
            "pbf_file": Path(pbf_path).name,
            "pbf_size_bytes": Path(pbf_path).stat().st_size,
            "pbf_sha256": _sha256_file(pbf_path),
            "osm_data_timestamp_utc": "2026-10-17T20:20:51Z",
        },
        "districts": sorted(district_boundaries["district"].astype(str).unique()),
        "network_type": NETWORK_TYPE,
        "target_crs": TARGET_CRS,
        "boundary_buffer_meters": BOUNDARY_BUFFER_METERS,
        "speed_method": (
            "OSM maxspeed tags where parseable; otherwise explicit uncalibrated "
            "prototype fallback speeds by highway class"
        ),
        "fallback_speed_kmh": FALLBACK_SPEEDS_KMH,
        "unknown_highway_fallback_kmh": UNKNOWN_HIGHWAY_FALLBACK_KMH,
        "node_count": int(len(nodes)),
        "directed_edge_count": int(len(edges)),
        "graphml": graph_path.name,
        "geopackage": gpkg_path.name,
        "geopackage_layers": ["road_edges", "road_nodes", "district_boundaries"],
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "osmnx_version": ox.__version__,
        "networkx_version": nx.__version__,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return graph_path, gpkg_path, manifest_path, manifest


def _sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_road_graph(
    pbf_path=PBF_PATH,
    boundaries_path=BOUNDARIES_PATH,
    output_dir=OUTPUT_DIR,
):
    _require_inputs(pbf_path, boundaries_path)
    boundaries, projected_boundaries, _, buffered_polygon = _load_target_polygon(
        boundaries_path
    )
    ox, graph = _extract_graph(pbf_path, buffered_polygon)
    _normalize_oneway_tags(graph)
    graph = ox.project_graph(graph, to_crs=TARGET_CRS)
    graph = ox.truncate.truncate_graph_polygon(
        graph,
        buffered_polygon,
        truncate_by_edge=True,
    )
    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise ValueError("The five-district road graph is empty after clipping")

    graph.graph["graph_from"] = "Geofabrik {}".format(Path(pbf_path).name)
    graph.graph["network_type"] = NETWORK_TYPE
    graph.graph["crs"] = TARGET_CRS
    graph = _assign_travel_times(ox, graph)
    _add_stable_edge_ids(graph)
    _clean_graph_attributes(graph)
    return _write_outputs(
        ox,
        graph,
        projected_boundaries,
        pbf_path=pbf_path,
        output_dir=output_dir,
    )


def main():
    try:
        graph_path, gpkg_path, manifest_path, manifest = build_road_graph()
    except (FileNotFoundError, ValueError, OSError, ImportError) as exc:
        print("Road graph build failed: {}".format(exc), file=sys.stderr)
        return 1

    print(
        "Built projected road graph: {} nodes, {} directed edges".format(
            manifest["node_count"], manifest["directed_edge_count"]
        )
    )
    print("GraphML: {}".format(graph_path))
    print("GeoPackage: {}".format(gpkg_path))
    print("Manifest: {}".format(manifest_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
