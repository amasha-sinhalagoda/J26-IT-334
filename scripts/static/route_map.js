(() => {
  "use strict";

  const form = document.querySelector("#route-form");
  const mode = document.querySelector("#mode");
  const rescueFields = document.querySelector("#rescue-fields");
  const evacuationFields = document.querySelector("#evacuation-fields");
  const submitButton = document.querySelector("#submit");
  const resultPanel = document.querySelector("#result");
  const resultTitle = document.querySelector("#result-title");
  const resultDetails = document.querySelector("#result-details");
  const mapStatus = document.querySelector("#map-status");

  let map;
  let routeSourceReady = false;
  let requestCounter = 0;

  function setMapStatus(message, visible = true) {
    mapStatus.textContent = message;
    mapStatus.hidden = !visible;
  }

  function addTextLine(parent, label, value) {
    const line = document.createElement("p");
    const heading = document.createElement("strong");
    heading.textContent = `${label}: `;
    line.append(heading, document.createTextNode(String(value)));
    parent.append(line);
  }

  function updateFormMode() {
    const rescueMode = mode.value === "rescue_dispatch";
    rescueFields.hidden = !rescueMode;
    evacuationFields.hidden = rescueMode;
    document.querySelector("#facility-id").required = rescueMode;
    document.querySelector("#incident-id").required = rescueMode;
    document.querySelector("#scenario-id").required = !rescueMode;
  }

  function emptyRoutes() {
    if (routeSourceReady) {
      map.getSource("route-results").setData({
        type: "FeatureCollection",
        features: [],
      });
    }
  }

  function showError(message) {
    resultPanel.hidden = false;
    resultPanel.dataset.status = "error";
    resultTitle.textContent = "Request failed";
    resultDetails.replaceChildren();
    addTextLine(resultDetails, "Details", message);
    setMapStatus("No route displayed", false);
  }

  function endpointFeature(coordinates, kind, label, color) {
    return {
      type: "Feature",
      properties: { kind, label, color },
      geometry: { type: "Point", coordinates },
    };
  }

  function buildRouteFeatures(result, routeType) {
    const features = [];
    const lineGeometries = [];

    function appendLine(geometry, properties) {
      if (!geometry || geometry.type !== "LineString"
          || !Array.isArray(geometry.coordinates)
          || geometry.coordinates.length < 2) {
        return;
      }
      const feature = {
        type: "Feature",
        properties,
        geometry,
      };
      features.push(feature);
      lineGeometries.push(geometry.coordinates);
    }

    if (routeType === "rescue_dispatch") {
      const route = result.route;
      appendLine(route && route.geometry, {
        role: "rescue",
        label: "Rescue dispatch route",
        color: "#c24136",
      });
      if (route && route.geometry && route.geometry.coordinates.length >= 2) {
        const coordinates = route.geometry.coordinates;
        features.push(
          endpointFeature(coordinates[0], "start", "Dispatch facility", "#137c8b"),
          endpointFeature(
            coordinates[coordinates.length - 1],
            "end",
            "Incident location",
            "#c24136",
          ),
        );
      }
    } else {
      for (const origin of result.origins || []) {
        for (const assignment of origin.assignments || []) {
          const geometry = assignment.route && assignment.route.geometry;
          const label = `${origin.origin_id} → ${assignment.shelter_name}`;
          appendLine(geometry, {
            role: "evacuation",
            label,
            color: "#1769aa",
          });
          if (geometry && Array.isArray(geometry.coordinates)
              && geometry.coordinates.length >= 2) {
            const coordinates = geometry.coordinates;
            features.push(
              endpointFeature(
                coordinates[0],
                "origin",
                origin.origin_id,
                "#137c8b",
              ),
              endpointFeature(
                coordinates[coordinates.length - 1],
                "shelter",
                assignment.shelter_name,
                "#328a57",
              ),
            );
          }
        }
      }
    }
    return { features, lineGeometries };
  }

  function fitToRoutes(lineGeometries) {
    if (!lineGeometries.length) {
      setMapStatus("No feasible route was returned.");
      return;
    }
    const bounds = new maplibregl.LngLatBounds();
    for (const line of lineGeometries) {
      for (const coordinate of line) {
        if (Array.isArray(coordinate) && coordinate.length >= 2
            && coordinate.every(Number.isFinite)) {
          bounds.extend(coordinate);
        }
      }
    }
    if (!bounds.isEmpty()) {
      map.fitBounds(bounds, { padding: 70, maxZoom: 14, duration: 500 });
    }
    setMapStatus(`${lineGeometries.length} route(s) displayed.`);
  }

  function showResult(payload) {
    const result = payload.result;
    const feasibleRoutes = buildRouteFeatures(result, payload.route_type);
    if (routeSourceReady) {
      map.getSource("route-results").setData({
        type: "FeatureCollection",
        features: feasibleRoutes.features,
      });
      fitToRoutes(feasibleRoutes.lineGeometries);
    } else {
      setMapStatus(
        "Map unavailable; the routing request completed but cannot be drawn.",
      );
    }

    resultPanel.hidden = false;
    resultPanel.dataset.status = result.status || "unknown";
    resultTitle.textContent = result.status === "feasible"
      ? "Route found"
      : result.status === "partial"
        ? "Partial evacuation plan"
        : "No feasible route";
    resultDetails.replaceChildren();
    addTextLine(resultDetails, "Mode", payload.route_type.replaceAll("_", " "));
    if (payload.alert_id) {
      addTextLine(resultDetails, "Alert", payload.alert_id);
    }
    addTextLine(resultDetails, "Status", result.status || "unknown");

    if (payload.route_type === "rescue_dispatch") {
      if (result.scenario_id) {
        addTextLine(resultDetails, "Scenario", result.scenario_id);
      }
      if (result.road_network_travel_time_seconds != null) {
        addTextLine(
          resultDetails,
          "Road travel time",
          `${Math.round(result.road_network_travel_time_seconds / 60)} min`,
        );
      }
      if (result.reason) {
        addTextLine(resultDetails, "Reason", result.reason);
      }
    } else {
      const demand = result.demand || {};
      addTextLine(resultDetails, "Origins", demand.origin_count ?? 0);
      addTextLine(resultDetails, "People served", demand.served_people ?? 0);
      addTextLine(
        resultDetails,
        "Unknown-demand origins",
        demand.unknown_demand_origin_count ?? 0,
      );
      if (result.scenario && result.scenario.scenario_id) {
        addTextLine(resultDetails, "Scenario", result.scenario.scenario_id);
      }
    }
    if (feasibleRoutes.lineGeometries.length === 0 && result.reason) {
      addTextLine(resultDetails, "Reason", result.reason);
    }
  }

  function addMapLayers() {
    map.addSource("route-results", {
      type: "geojson",
      data: { type: "FeatureCollection", features: [] },
    });
    map.addLayer({
      id: "route-lines",
      type: "line",
      source: "route-results",
      filter: ["==", ["geometry-type"], "LineString"],
      paint: {
        "line-color": ["get", "color"],
        "line-width": 5,
        "line-opacity": 0.9,
      },
      layout: { "line-cap": "round", "line-join": "round" },
    });
    map.addLayer({
      id: "route-points",
      type: "circle",
      source: "route-results",
      filter: ["==", ["geometry-type"], "Point"],
      paint: {
        "circle-color": ["get", "color"],
        "circle-radius": 7,
        "circle-stroke-color": "#ffffff",
        "circle-stroke-width": 2,
      },
    });
    map.on("click", "route-points", (event) => {
      const feature = event.features && event.features[0];
      if (!feature) {
        return;
      }
      const content = document.createElement("div");
      const heading = document.createElement("strong");
      heading.textContent = feature.properties.label || feature.properties.kind;
      content.append(heading);
      new maplibregl.Popup()
        .setLngLat(event.lngLat)
        .setDOMContent(content)
        .addTo(map);
    });
    map.on("mouseenter", "route-points", () => {
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "route-points", () => {
      map.getCanvas().style.cursor = "";
    });
    routeSourceReady = true;
  }

  function initializeMap() {
    if (typeof maplibregl === "undefined") {
      setMapStatus("MapLibre could not load. Check network access to the map library.");
      return;
    }
    map = new maplibregl.Map({
      container: "map",
      center: [80.72, 7.87],
      zoom: 6.2,
      style: {
        version: 8,
        sources: {
          osm: {
            type: "raster",
            tiles: [
              "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
            ],
            tileSize: 256,
            attribution:
              "© <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap contributors</a>",
          },
        },
        layers: [{
          id: "osm-raster",
          type: "raster",
          source: "osm",
          minzoom: 0,
          maxzoom: 19,
        }],
      },
      maxZoom: 18,
    });
    map.addControl(new maplibregl.NavigationControl(), "top-right");
    map.on("load", () => {
      addMapLayers();
      setMapStatus("Map ready.", false);
    });
    map.on("error", (event) => {
      if (event.error) {
        setMapStatus("Map service error; route requests remain available.");
      }
    });
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const currentRequest = ++requestCounter;
    const formData = new FormData(form);
    const requestMode = String(formData.get("mode"));
    const alertId = String(formData.get("alert_id") || "").trim();
    const payload = requestMode === "rescue_dispatch"
      ? {
        mode: requestMode,
        facility_id: String(formData.get("facility_id") || "").trim(),
        incident_record_id: String(
          formData.get("incident_record_id") || "",
        ).trim(),
      }
      : {
        mode: requestMode,
        scenario_id: String(formData.get("scenario_id") || "").trim(),
      };
    if (alertId) {
      payload.alert_id = alertId;
    }

    submitButton.disabled = true;
    submitButton.textContent = "Finding route…";
    resultPanel.hidden = true;
    emptyRoutes();
    try {
      const response = await fetch("/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = await response.json();
      if (currentRequest !== requestCounter) {
        return;
      }
      if (!response.ok) {
        const detail = body.detail || `Request failed with HTTP ${response.status}`;
        throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
      }
      showResult(body);
    } catch (error) {
      if (currentRequest === requestCounter) {
        showError(error instanceof Error ? error.message : String(error));
      }
    } finally {
      if (currentRequest === requestCounter) {
        submitButton.disabled = false;
        submitButton.textContent = "Find route";
      }
    }
  });

  mode.addEventListener("change", updateFormMode);
  updateFormMode();
  initializeMap();
})();
