import unittest

from pyproj import CRS

from scripts.load_routing_data_postgis import (
    TARGET_SRID,
    _matches_target_projection,
    _quoted,
)


class PostGISLoaderTests(unittest.TestCase):
    def test_recognizes_nbri_kandawala_crs_as_epsg_5234(self):
        source_crs = CRS.from_proj4(
            "+proj=tmerc +lat_0=7.0004802778 +lon_0=80.7717111111111 "
            "+k=0.9999238418 +x_0=200000 +y_0=200000 "
            "+ellps=evrst30 +units=m +no_defs"
        )
        target_crs = CRS.from_epsg(TARGET_SRID)

        self.assertTrue(_matches_target_projection(source_crs, target_crs))

    def test_rejects_a_different_projection(self):
        self.assertFalse(
            _matches_target_projection(
                CRS.from_epsg(4326),
                CRS.from_epsg(TARGET_SRID),
            )
        )

    def test_quotes_valid_sql_identifiers(self):
        self.assertEqual('"road_edges"', _quoted("road_edges"))

    def test_rejects_unsafe_sql_identifiers(self):
        with self.assertRaises(ValueError):
            _quoted('roads"; DROP SCHEMA public; --')


if __name__ == "__main__":
    unittest.main()
