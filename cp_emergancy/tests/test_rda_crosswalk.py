import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

from build_rda_crosswalk import (
    _add_edge_crosswalk_fields,
    build_crosswalk,
    normalize_route_code,
)


RDA_ROADS = pd.DataFrame([
    {
        "Route Number": "AA001",
        "Road Class": "A",
        "Sub-class": "AA",
        "Road Name": "Colombo - Kandy",
        "Road Length (km)": 115.85,
    },
    {
        "Route Number": "AB001",
        "Road Class": "A",
        "Sub-class": "AB",
        "Road Name": "Ampara - Inginiyagala",
        "Road Length (km)": 19.79,
    },
    {
        "Route Number": "AC001",
        "Road Class": "A",
        "Sub-class": "AC",
        "Road Name": "Approach Road",
        "Road Length (km)": 1.61,
    },
    {
        "Route Number": "B027",
        "Road Class": "B",
        "Sub-class": "B",
        "Road Name": "Example B road",
        "Road Length (km)": 12.0,
    },
    {
        "Route Number": "E001",
        "Road Class": "E",
        "Sub-class": "E",
        "Road Name": "Expressway",
        "Road Length (km)": 10.0,
    },
])


class RdaCrosswalkTests(unittest.TestCase):
    def test_route_code_normalization_only_removes_numeric_leading_zeroes(self):
        self.assertEqual(normalize_route_code(" b027 "), "B27")
        self.assertEqual(normalize_route_code("E001"), "E1")
        self.assertEqual(normalize_route_code("AB011"), "AB11")
        self.assertEqual(normalize_route_code("B27-12"), "B27-12")
        self.assertIsNone(normalize_route_code(None))

    def test_direct_match_and_ambiguous_a_subclass_are_not_conflated(self):
        crosswalk = build_crosswalk(
            ["B27", "A1", "E001", "B27-12"],
            RDA_ROADS,
            {"B27": 12, "A1": 20, "E001": 3, "B27-12": 2},
        ).set_index("osm_ref")

        self.assertEqual(crosswalk.loc["B27", "rda_code"], "B027")
        self.assertEqual(
            crosswalk.loc["B27", "match_status"],
            "matched_normalized_code",
        )
        self.assertEqual(
            crosswalk.loc["E001", "rda_code"],
            "E001",
        )
        self.assertTrue(pd.isna(crosswalk.loc["A1", "rda_code"]))
        self.assertEqual(
            crosswalk.loc["A1", "match_status"],
            "ambiguous_a_subclass",
        )
        self.assertEqual(
            crosswalk.loc["A1", "candidate_codes"],
            '["AA001", "AB001", "AC001"]',
        )
        self.assertEqual(crosswalk.loc["B27-12", "match_status"], "unmatched")

    def test_attached_edge_metadata_preserves_unmatched_status(self):
        edges = pd.DataFrame({
            "ref": ["B27", "A1", None],
        })
        crosswalk = build_crosswalk(["B27", "A1"], RDA_ROADS)

        result = _add_edge_crosswalk_fields(edges, crosswalk)

        self.assertEqual(result.loc[0, "rda_code"], "B027")
        self.assertEqual(result.loc[0, "rda_class"], "B")
        self.assertEqual(result.loc[1, "rda_match_status"], "ambiguous_a_subclass")
        self.assertEqual(result.loc[1, "rda_candidate_codes"], '["AA001", "AB001", "AC001"]')
        self.assertEqual(result.loc[2, "rda_match_status"], "missing_osm_ref")

    def test_duplicate_rda_codes_after_normalization_are_rejected(self):
        roads = pd.concat([
            RDA_ROADS,
            RDA_ROADS.iloc[[3]].assign(**{"Route Number": "B27"}),
        ], ignore_index=True)

        with self.assertRaisesRegex(ValueError, "collide after normalization"):
            build_crosswalk(["B27"], roads)


if __name__ == "__main__":
    unittest.main()
