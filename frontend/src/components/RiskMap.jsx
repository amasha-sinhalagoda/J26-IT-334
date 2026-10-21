
import { useEffect, useMemo, useState } from "react";
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  ScaleControl,
  useMap,
} from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const PRIORITY_COLORS = {
  "Very High": "#dc2626",
  High: "#f97316",
  Moderate: "#eab308",
  Low: "#22c55e",
};

const LANDSLIDE_COLOR = "#8b5cf6";
const UNASSESSED_COLOR = "#cbd5e1";

function getPriorityColor(level) {
  return PRIORITY_COLORS[level] || "#64748b";
}

function getLocation(feature) {
  const properties = feature?.properties || {};

  return {
    district: String(properties.District || "").trim(),
    division: String(properties.Division || "").trim(),
  };
}

function getLocationKey(district, division) {
  return `${district}|${division}`.toLowerCase();
}

// Automatically zoom to a searched or clicked DS Division.
function MapZoomController({ selectedFeature }) {
  const map = useMap();

  useEffect(() => {
    if (!selectedFeature) return;

    const layer = L.geoJSON(selectedFeature);
    const bounds = layer.getBounds();

    if (bounds.isValid()) {
      map.fitBounds(bounds, {
        padding: [35, 35],
        maxZoom: 12,
        animate: true,
      });
    }
  }, [map, selectedFeature]);

  return null;
}

export default function RiskMap({ onSelectDivision }) {
  const [dsBoundaries, setDsBoundaries] = useState(null);
  const [floodGeojson, setFloodGeojson] = useState(null);
  const [landslideGeojson, setLandslideGeojson] = useState(null);

  const [selectedDivision, setSelectedDivision] = useState(null);
  const [selectedFeature, setSelectedFeature] = useState(null);

  const [searchQuery, setSearchQuery] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);

  const [error, setError] = useState("");

  // Load the existing GIS layers.
  useEffect(() => {
    let cancelled = false;

    async function loadLayers() {
      try {
        const [
          boundaryResponse,
          floodResponse,
          landslideResponse,
        ] = await Promise.all([
          fetch("/data/sri_lanka_ds_boundaries.geojson"),
          fetch("/data/flood_ds_priority_map.geojson"),
          fetch("/data/landslide_ds_boundaries.geojson"),
        ]);

        if (
          !boundaryResponse.ok ||
          !floodResponse.ok ||
          !landslideResponse.ok
        ) {
          throw new Error("Could not load GIS boundary layers.");
        }

        const [
          boundaryData,
          floodData,
          landslideData,
        ] = await Promise.all([
          boundaryResponse.json(),
          floodResponse.json(),
          landslideResponse.json(),
        ]);

        if (!cancelled) {
          setDsBoundaries(boundaryData);
          setFloodGeojson(floodData);
          setLandslideGeojson(landslideData);
          setError("");
        }
      } catch (err) {
        if (!cancelled) {
          setError(err.message);
        }
      }
    }

    loadLayers();

    return () => {
      cancelled = true;
    };
  }, []);

  // Combine DS locations from all available GIS layers.
  const locations = useMemo(() => {
    const unique = new Map();

    const sources = [
      {
        data: dsBoundaries,
        hazardType: "background",
      },
      {
        data: floodGeojson,
        hazardType: "flood",
      },
      {
        data: landslideGeojson,
        hazardType: "landslide",
      },
    ];

    for (const source of sources) {
      for (const feature of source.data?.features || []) {
        const { district, division } = getLocation(feature);

        if (!district || !division) continue;

        const key = getLocationKey(district, division);

        if (!unique.has(key)) {
          unique.set(key, {
            district,
            division,
            feature,
            hazardType: source.hazardType,
          });
        } else if (source.hazardType !== "background") {
          // Prefer a study-area feature when available.
          unique.set(key, {
            district,
            division,
            feature,
            hazardType: source.hazardType,
          });
        }
      }
    }

    return Array.from(unique.values()).sort((a, b) =>
      a.division.localeCompare(b.division)
    );
  }, [dsBoundaries, floodGeojson, landslideGeojson]);

  // Autocomplete matches district, division, or both.
  const searchResults = useMemo(() => {
    const query = searchQuery.trim().toLowerCase();

    if (!query) return [];

    return locations
      .filter(({ district, division }) => {
        const combined = `${division} ${district}`.toLowerCase();

        return (
          combined.includes(query) ||
          district.toLowerCase().includes(query) ||
          division.toLowerCase().includes(query)
        );
      })
      .slice(0, 10);
  }, [locations, searchQuery]);

  function selectLocation(location, method = "search") {
    const {
      district,
      division,
      feature,
      hazardType,
    } = location;

    const properties = feature?.properties || {};

    const level =
      hazardType === "flood"
        ? properties.priority_level || "Not assessed"
        : "Not assessed";

    const score =
      hazardType === "flood" &&
      properties.priority_score != null
        ? Number(properties.priority_score).toFixed(3)
        : "Not assessed";

    setSelectedDivision({
      district,
      division,
      hazardType,
      level,
      score,
      method,
    });

    setSelectedFeature(feature || null);
    setSearchQuery(`${division}, ${district}`);
    setShowSuggestions(false);

    // Preserve the existing dashboard integration.
    if (onSelectDivision) {
      onSelectDivision({ district, division });
    }
  }

  function onEachFeature(feature, layer, hazardType) {
    const { district, division } = getLocation(feature);

    if (!district || !division) return;

    const properties = feature.properties || {};

    const label =
      hazardType === "landslide"
        ? "Landslide study area (boundary only)"
        : `Simulated flood priority: ${
            properties.priority_level || "Not assessed"
          }`;

    layer.bindTooltip(
      `${division}, ${district} — ${label}`,
      { sticky: true }
    );

    layer.on("click", () => {
      selectLocation(
        {
          district,
          division,
          feature,
          hazardType,
        },
        "map"
      );
    });
  }

  function styleBackgroundBoundary() {
    return {
      color: "#475569",
      weight: 1.2,
      fillColor: "#94a3b8",
      fillOpacity: 0.65,
    };
  }

  function styleFloodFeature(feature) {
    const level = feature.properties?.priority_level;

    return {
      color: "#e2e8f0",
      weight: 1,
      fillColor: getPriorityColor(level),
      fillOpacity: 0.55,
    };
  }

  function styleLandslideFeature() {
    return {
      color: "#6d28d9",
      weight: 2,
      fillColor: LANDSLIDE_COLOR,
      fillOpacity: 0.4,
    };
  }

  function styleSelectedFeature() {
    return {
      color: "#0f172a",
      weight: 4,
      fillColor: "#38bdf8",
      fillOpacity: 0.22,
      dashArray: "7 5",
    };
  }

  const gisLoaded =
    dsBoundaries && floodGeojson && landslideGeojson;

  return (
    <div className="risk-map-panel">
      <div className="risk-map-header">
        <div>
          <h2>Interactive Multi-Hazard GIS Map</h2>
          <p>
            Sri Lanka — DS Division flood scenarios and
            landslide study-area boundaries
          </p>
        </div>

        <span className="map-status">
          {gisLoaded
            ? "GIS Layers Loaded"
            : error
              ? "GIS Load Error"
              : "Loading GIS Layers"}
        </span>
      </div>

      {error && (
        <p style={{ color: "#fca5a5" }}>
          {error}
        </p>
      )}

      {/* Location search */}
      <div
        style={{
          position: "relative",
          margin: "18px 0",
        }}
      >
        <label
          htmlFor="ds-location-search"
          style={{
            display: "block",
            marginBottom: "8px",
            fontWeight: 600,
          }}
        >
          Search District or DS Division
        </label>

        <input
          id="ds-location-search"
          type="search"
          value={searchQuery}
          placeholder="Search e.g. Ratnapura, Colombo, Nuwara Eliya"
          autoComplete="off"
          onChange={(event) => {
            setSearchQuery(event.target.value);
            setShowSuggestions(true);
          }}
          onFocus={() => setShowSuggestions(true)}
          onKeyDown={(event) => {
            if (
              event.key === "Enter" &&
              showSuggestions &&
              searchResults.length > 0
            ) {
              event.preventDefault();
              selectLocation(searchResults[0]);
            }

            if (event.key === "Escape") {
              setShowSuggestions(false);
            }
          }}
          style={{
            width: "100%",
            padding: "13px 15px",
            borderRadius: "10px",
            border: "1px solid #94a3b8",
            background: "#ffffff",
            color: "#0f172a",
            fontSize: "14px",
            outlineOffset: "2px",
          }}
        />

        {showSuggestions && searchQuery.trim() && (
          <div
            style={{
              position: "absolute",
              top: "100%",
              left: 0,
              right: 0,
              zIndex: 1100,
              background: "#ffffff",
              color: "#0f172a",
              border: "1px solid #cbd5e1",
              borderRadius: "10px",
              boxShadow: "0 8px 22px rgba(0,0,0,0.15)",
              maxHeight: "260px",
              overflowY: "auto",
              marginTop: "4px",
            }}
          >
            {searchResults.length > 0 ? (
              searchResults.map((location) => (
                <button
                  key={getLocationKey(
                    location.district,
                    location.division
                  )}
                  type="button"
                  onClick={() => selectLocation(location)}
                  style={{
                    display: "block",
                    width: "100%",
                    padding: "12px 15px",
                    border: "none",
                    borderBottom: "1px solid #e2e8f0",
                    background: "#ffffff",
                    color: "#0f172a",
                    textAlign: "left",
                    cursor: "pointer",
                  }}
                >
                  <strong>{location.division}</strong>
                  <span style={{ color: "#64748b" }}>
                    {" — "}
                    {location.district} District
                  </span>
                </button>
              ))
            ) : (
              <div
                style={{
                  padding: "12px 15px",
                  color: "#64748b",
                }}
              >
                No matching DS Division found.
              </div>
            )}
          </div>
        )}

        <p
          style={{
            marginTop: "7px",
            fontSize: "12px",
            opacity: 0.8,
          }}
        >
          Type a location and select a result to zoom to
          its DS Division boundary.
        </p>
      </div>

      {/* Existing interactive map */}
      <div className="risk-map-container">
        <MapContainer
          center={[7.2, 80.3]}
          zoom={7}
          minZoom={6}
          maxZoom={16}
          scrollWheelZoom={true}
          style={{
            height: "100%",
            width: "100%",
          }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          <MapZoomController
            selectedFeature={selectedFeature}
          />

          {/* Complete DS boundaries */}
          {dsBoundaries && (
            <GeoJSON
              data={dsBoundaries}
              style={styleBackgroundBoundary}
              interactive={false}
            />
          )}

          {/* Simulated flood-priority layer */}
          {floodGeojson && (
            <GeoJSON
              data={floodGeojson}
              style={styleFloodFeature}
              onEachFeature={(feature, layer) =>
                onEachFeature(feature, layer, "flood")
              }
            />
          )}

          {/* Landslide study-area boundaries */}
          {landslideGeojson && (
            <GeoJSON
              data={landslideGeojson}
              style={styleLandslideFeature}
              onEachFeature={(feature, layer) =>
                onEachFeature(feature, layer, "landslide")
              }
            />
          )}

          {/* Highlight the selected DS Division */}
          {selectedFeature && (
            <GeoJSON
              key={getLocationKey(
                selectedDivision?.district || "",
                selectedDivision?.division || ""
              )}
              data={selectedFeature}
              style={styleSelectedFeature}
              interactive={false}
            />
          )}

          <ScaleControl position="bottomleft" />
        </MapContainer>
      </div>

      {/* Existing legend */}
      <div className="gis-legend">
        <span>
          <i style={{ background: "#dc2626" }} />
          Very High — Flood
        </span>

        <span>
          <i style={{ background: "#f97316" }} />
          High — Flood
        </span>

        <span>
          <i style={{ background: "#eab308" }} />
          Moderate — Flood
        </span>

        <span>
          <i style={{ background: "#22c55e" }} />
          Low — Flood
        </span>

        <span>
          <i style={{ background: LANDSLIDE_COLOR }} />
          Landslide study area — Not assessed
        </span>

        <span>
          <i style={{ background: UNASSESSED_COLOR }} />
          Other DS divisions — Not assessed
        </span>
      </div>

      {/* Selected location information */}
      {selectedDivision && (
        <div className="selected-ds-panel">
          <h3>Selected DS Division</h3>

          <p>
            <strong>District:</strong>{" "}
            {selectedDivision.district}
          </p>

          <p>
            <strong>Division:</strong>{" "}
            {selectedDivision.division}
          </p>

          <p>
            <strong>Selection method:</strong>{" "}
            {selectedDivision.method === "search"
              ? "Location search"
              : "Interactive map"}
          </p>

          <p>
            <strong>GIS layer:</strong>{" "}
            {selectedDivision.hazardType === "landslide"
              ? "Landslide study-area boundary"
              : selectedDivision.hazardType === "flood"
                ? "Simulated flood-priority layer"
                : "General DS boundary — Not assessed"}
          </p>

          <p>
            <strong>
              {selectedDivision.hazardType === "flood"
                ? "Simulated flood priority:"
                : "Map risk assessment:"}
            </strong>{" "}
            {selectedDivision.level}
          </p>

          {selectedDivision.hazardType === "flood" && (
            <p>
              <strong>Priority score:</strong>{" "}
              {selectedDivision.score}
            </p>
          )}
        </div>
      )}

    
    </div>
  );
}
