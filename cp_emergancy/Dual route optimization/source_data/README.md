# Dual-route source data

## OpenStreetMap road source

- Provider: [Geofabrik Sri Lanka download](https://download.geofabrik.de/asia/sri-lanka.html)
- Local file: `sri-lanka-261017.osm.pbf`
- Pinned extract URL: <https://download.geofabrik.de/asia/sri-lanka-261017.osm.pbf>
- OSM data timestamp reported by Geofabrik: 2026-10-17 20:20:51 UTC
- File size: 144,465,650 bytes
- MD5: `c5d06aca9a48067a1a821980d3e95a31`
- SHA-256: `5b923c1e27c2cf536a042c2514461b3fbca05797913c8c3d1a783b03f122f149`
- Attribution/licence: © OpenStreetMap contributors, ODbL. See
  <https://www.openstreetmap.org/copyright>.

The large PBF is ignored by Git. Keep this metadata with the project and
re-download the pinned dated URL if the local extract is missing.

## District boundaries

- Provider: [geoBoundaries Sri Lanka ADM2](https://www.geoboundaries.org/)
- Local file: `geoBoundaries-LKA-ADM2.geojson`
- Pinned source commit:
  <https://github.com/wmgeolab/geoBoundaries/tree/9469f09592ced973a3448cf66b6100b741b64c0d/releaseData/gbOpen/LKA/ADM2>
- Source data update: 2023-01-19; build date: 2023-12-12
- Represented boundary year: 2017
- CRS: CRS84 / WGS84 longitude-latitude
- SHA-256: `47b5ae26225e62052686b6a7ab1dadcaab96d7b968f618b752151f4dc8943a4d`
- Licence: Open Data Commons Open Database License (ODbL) 1.0.

Preprocessing selects the Ratnapura, Kegalle, Kalutara, Badulla, and Nuwara
Eliya ADM2 features into `processed_data/dual_route/district_boundaries.geojson`.

## Nuwara Eliya LHMP

The source LHMP is the NBRI `Nuwara_Eliya_LHMP_50000` shapefile in the
`NuwaraEliya(SLIIT)-(Bagya)` data package. It uses the Sri Lanka Kandawala
projection (EPSG:5234). Preprocessing copies the complete shapefile bundle,
including its projection and attribute sidecars, to
`processed_data/dual_route/nuwara_eliya_lhmp/` without changing its source
attributes.
