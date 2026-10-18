import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR / "scripts"))

from preprocess_dual_route_data import (
    _validate_coordinates,
    _validate_wkt,
    load_routing_tables,
    write_preprocessed_data,
)


class DualRoutePreprocessingTests(unittest.TestCase):
    def test_supplied_workbooks_validate_and_preserve_provenance(self):
        tables = load_routing_tables()

        self.assertEqual(len(tables), 8)
        self.assertEqual(
            tables["incident_points"]["source_type"].value_counts().to_dict(),
            {"synthetic": 951, "official": 1205},
        )
        self.assertEqual(
            tables["evacuation_origins"]["source_type"].value_counts().to_dict(),
            {"synthetic": 420, "official": 507},
        )
        self.assertEqual(
            tables["incident_points"]["incident_id"].duplicated().sum(),
            6,
        )
        self.assertTrue(
            tables["incident_points"]["incident_record_id"].is_unique
        )
        self.assertTrue(tables["road_closures"]["is_synthetic"].all())
        self.assertEqual(
            set(tables["lhmp_zones"]["district"]),
            {"Ratnapura", "Kegalle", "Kalutara", "Badulla"},
        )

    def test_preprocessing_writes_all_tables_and_provenance_report(self):
        tables = load_routing_tables()
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = write_preprocessed_data(tables, temp_dir)

            for dataset in tables:
                output = pd.read_csv(output_dir / "{}.csv".format(dataset))
                self.assertEqual(len(output), len(tables[dataset]))
                self.assertIn("source_type", output.columns)
                self.assertIn("is_synthetic", output.columns)

            report = (output_dir / "preprocessing_report.txt").read_text(
                encoding="utf-8"
            )
            self.assertIn("not observed events or operational closure evidence", report)
            self.assertIn("Nuwara Eliya NBRI shapefile", report)

    def test_coordinate_validation_rejects_points_outside_sri_lanka(self):
        frame = pd.DataFrame({"lat": [6.0, 30.0], "lon": [80.0, 80.0]})

        with self.assertRaisesRegex(ValueError, "outside Sri Lanka bounds"):
            _validate_coordinates(frame, "test_points", "lat", "lon")

    def test_wkt_validation_rejects_unbalanced_geometry(self):
        frame = pd.DataFrame([{
            "geometry_crs": "EPSG:5234",
            "geometry_wkt": "MULTIPOLYGON (((1 1, 2 2))",
        }])

        with self.assertRaisesRegex(ValueError, "unbalanced WKT parentheses"):
            _validate_wkt(frame, "test_polygons", "MULTIPOLYGON")

    def test_wkt_validation_rejects_unexpected_crs(self):
        frame = pd.DataFrame([{
            "geometry_crs": "EPSG:4326",
            "geometry_wkt": "LINESTRING (1 1, 2 2)",
        }])

        with self.assertRaisesRegex(ValueError, "must use EPSG:5234"):
            _validate_wkt(frame, "test_lines", "LINESTRING")


if __name__ == "__main__":
    unittest.main()
