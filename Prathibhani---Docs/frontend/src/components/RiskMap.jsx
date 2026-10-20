
import { useEffect, useState } from "react";
import {
  MapContainer,
  TileLayer,
  GeoJSON,
  ScaleControl,
} from "react-leaflet";
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

export default function RiskMap({ onSelectDivision }) {
  const [dsBoundaries, setDsBoundaries] = useState(null);
  const [floodGeojson, setFloodGeojson] = useState(null);
  const [landslideGeojson, setLandslideGeojson] = useState(null);
  const [selectedDivision, setSelectedDivision] = useState(null);
  const [error, setError] = useState("");

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

  // Existing flood and landslide interactions
  function onEachFeature(feature, layer) {
    const properties = feature.properties || {};

    const district = properties.District || "Unknown";
    const division = properties.Division || "Unknown";

    const isLandslide =
      properties.hazard_type === "landslide";

    const level = isLandslide
      ? "Not assessed"
      : properties.priority_level || "Unknown";

    const score = properties.priority_score;

    const scoreText =
      !isLandslide && score != null
        ? Number(score).toFixed(3)
        : "Not assessed";

    layer.bindTooltip(
      `${division}, ${district} — ${
        isLandslide
          ? "Landslide study area (boundary only)"
          : "Simulated flood priority"
      }`,
      { sticky: true }
    );

    layer.on("click", () => {
      setSelectedDivision({
        district,
        division,
        hazardType: isLandslide ? "landslide" : "flood",
        level,
        score: scoreText,
      });

      if (onSelectDivision) {
        onSelectDivision({ district, division });
      }
    });
  }

  // Background DS boundaries
  function styleBackgroundBoundary() {
    return {
      color: "#475569",
      weight: 1.2,
      fillColor: "#94a3b8",
      fillOpacity: 0.65,
    };
  }

  // Existing flood priority styling
  function styleFloodFeature(feature) {
    const level = feature.properties?.priority_level;

    return {
      color: "#e2e8f0",
      weight: 1,
      fillColor: getPriorityColor(level),
      fillOpacity: 0.55,
    };
  }

  // Existing landslide study-area styling
  function styleLandslideFeature() {
    return {
      color: "#6d28d9",
      weight: 2,
      fillColor: LANDSLIDE_COLOR,
      fillOpacity: 0.4,
    };
  }

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
          {dsBoundaries && floodGeojson && landslideGeojson
            ? "GIS Layers Loaded"
            : error
              ? "GIS Load Error"
              : "Loading GIS Layers"}
        </span>
      </div>

      {error && (
        <p style={{ color: "#fca5a5" }}>{error}</p>
      )}

      <div className="risk-map-container">
        <MapContainer
          center={[7.2, 80.3]}
          zoom={7}
          minZoom={6}
          maxZoom={16}
          scrollWheelZoom={true}
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {/* Complete DS boundaries in light gray */}
          {dsBoundaries && (
            <GeoJSON
              data={dsBoundaries}
              style={styleBackgroundBoundary}
              interactive={false}
            />
          )}

          {/* Existing flood priority polygons */}
          {floodGeojson && (
            <GeoJSON
              data={floodGeojson}
              style={styleFloodFeature}
              onEachFeature={onEachFeature}
            />
          )}

          {/* Existing landslide study-area polygons */}
          {landslideGeojson && (
            <GeoJSON
              data={landslideGeojson}
              style={styleLandslideFeature}
              onEachFeature={onEachFeature}
            />
          )}

          <ScaleControl position="bottomleft" />
        </MapContainer>
      </div>

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
            <strong>GIS layer:</strong>{" "}
            {selectedDivision.hazardType === "landslide"
              ? "Landslide study-area boundary"
              : "Simulated flood-priority layer"}
          </p>

          <p>
            <strong>
              {selectedDivision.hazardType === "landslide"
                ? "Landslide risk:"
                : "Simulated flood priority:"}
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

      <p className="map-footnote">
        Research demonstration. Flood colors represent simulated
        priority values, not live forecasts. Purple areas show
        Nuwara Eliya landslide study-area boundaries only;
        no landslide risk classification is assigned by this map.
        Gray boundaries represent areas not assessed in the
        displayed scenarios. Neither layer represents an
        official warning.
      </p>
    </div>
  );
}
