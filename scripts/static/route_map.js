(() => {
  "use strict";

  const $ = (selector) => document.querySelector(selector);
  const mapStatus = $("#map-status");
  const resultList = $("#result-list");
  const detailStats = $("#detail-stats");
  const metrics = $("#metrics");
  const routeForm = $("#route-form");
  const mode = $("#mode");
  const routeSubmit = $("#route-submit");
  const dispatchSubmit = $("#dispatch-submit");
  let map;
  let sourcesReady = false;
  let pendingFeatures = [];
  let activeView = "dispatch";
  let dispatchData = null;
  let requestCounter = 0;

  function status(message, visible = true) {
    mapStatus.textContent = message;
    mapStatus.hidden = !visible;
  }

  function textLine(parent, label, value) {
    const row = document.createElement("div");
    row.className = "stat-line";
    const name = document.createElement("span");
    const content = document.createElement("strong");
    name.textContent = label;
    content.textContent = value == null || value === "" ? "—" : String(value);
    row.append(name, content);
    parent.append(row);
  }

  function setMetrics(items) {
    metrics.replaceChildren();
    for (const [value, label] of items) {
      const card = document.createElement("div");
      card.className = "metric";
      const strong = document.createElement("strong");
      const span = document.createElement("span");
      strong.textContent = String(value);
      span.textContent = label;
      card.append(strong, span);
      metrics.append(card);
    }
  }

  function pointFeature(coordinates, properties) {
    if (!Array.isArray(coordinates) || coordinates.length < 2
        || coordinates.some((value) => value == null || value === "")
        || !coordinates.every((value) => Number.isFinite(Number(value)))) return null;
    return { type: "Feature", properties, geometry: { type: "Point", coordinates: coordinates.map(Number) } };
  }

  function routeFeature(geometry, properties) {
    if (!geometry || geometry.type !== "LineString"
        || !Array.isArray(geometry.coordinates) || geometry.coordinates.length < 2) return null;
    return { type: "Feature", properties, geometry };
  }

  function setFeatures(features, zoom = true) {
    pendingFeatures = features.filter(Boolean);
    if (!sourcesReady) return;
    map.getSource("results").setData({ type: "FeatureCollection", features: pendingFeatures });
    if (!zoom) return;
    const bounds = new maplibregl.LngLatBounds();
    let count = 0;
    for (const feature of pendingFeatures) {
      const geometry = feature.geometry;
      const coordinates = geometry.type === "Point" ? [geometry.coordinates]
        : geometry.type === "LineString" ? geometry.coordinates : [];
      for (const coordinate of coordinates) {
        if (Array.isArray(coordinate) && coordinate.length >= 2
            && coordinate.slice(0, 2).every(Number.isFinite)) {
          bounds.extend(coordinate.slice(0, 2));
          count += 1;
        }
      }
    }
    if (count) map.fitBounds(bounds, { padding: { top: 100, right: 330, bottom: 120, left: 330 }, maxZoom: 12, duration: 450 });
  }

  function dispatchFilters() {
    if (!dispatchData) return { allocations: [], requests: [] };
    const district = $("#district-filter").value;
    const hazard = $("#hazard-filter").value;
    const resource = $("#resource-filter").value;
    const allocationRows = dispatchData.allocations.filter((row) =>
      (district === "All districts" || row.district === district)
      && (hazard === "All hazards" || row.hazard_type === hazard)
      && (resource === "All resources" || row.requested_resource_type === resource));
    const requestRows = dispatchData.requests.filter((row) =>
      (district === "All districts" || row.district === district)
      && (hazard === "All hazards" || row.hazard_type === hazard)
      && (resource === "All resources" || row.requested_resource_type === resource));
    return { allocations: allocationRows, requests: requestRows };
  }

  function makeDispatchFeatures() {
    const filtered = dispatchFilters();
    const features = [];
    const showRequests = $("#show-requests").checked;
    const showResources = $("#show-resources").checked;
    if (showRequests) {
      for (const row of filtered.requests) {
        const feature = pointFeature([row.longitude, row.latitude], {
          kind: "request",
          label: row.alert_id,
          district: row.district,
          hazard: row.hazard_type,
          resource: row.requested_resource_type,
          allocated: Number(row.allocated_quantity || 0),
          requested: Number(row.requested_quantity || 0),
          unfilled: Number(row.unfilled_quantity || 0),
        });
        if (feature) features.push(feature);
      }
    }
    if (showResources) {
      for (const row of filtered.allocations) {
        const feature = pointFeature([row.resource_longitude, row.resource_latitude], {
          kind: "resource",
          label: row.resource_id,
          district: row.resource_district,
          alert: row.alert_id,
          resource: row.requested_resource_type,
          quantity: Number(row.allocated_quantity || 0),
        });
        if (feature) features.push(feature);
      }
    }
    setFeatures(features);
    renderDispatchList(filtered.allocations, filtered.requests);
    const allDistricts = new Set(filtered.requests.map((row) => row.district).filter(Boolean));
    const coveredDistricts = new Set(filtered.allocations.map((row) => row.district).filter(Boolean));
    setMetrics([
      [filtered.requests.length, "Requests in view"],
      [`${coveredDistricts.size}/${allDistricts.size}`, "Districts receiving units"],
      [filtered.allocations.reduce((sum, row) => sum + Number(row.allocated_quantity || 0), 0), "Units proposed"],
      [filtered.requests.reduce((sum, row) => sum + Number(row.unfilled_quantity || 0), 0), "Units unfilled"],
    ]);
    status(`${features.length} map records · allocation preview`);
  }

  function renderDispatchList(allocations, requests) {
    $("#inspector-kicker").textContent = "Workbook inventory snapshot";
    $("#inspector-title").textContent = "Allocation preview";
    $("#inspector-copy").textContent = "Priority and local scarcity guide the proposed assignments. Select a request or resource marker for details.";
    $("#list-title").textContent = "Proposed assignments";
    detailStats.replaceChildren();
    textLine(detailStats, "Pending request rows", dispatchData.summary.pending_requests);
    textLine(detailStats, "Inventory source", "Workbook snapshot");
    textLine(detailStats, "Existing reservation records", dispatchData.reservation_records);
    resultList.replaceChildren();
    const rows = allocations.slice(0, 14);
    if (!rows.length) {
      const empty = document.createElement("div");
      empty.className = "subtle";
      empty.textContent = requests.length ? "No assignments match these filters." : "No requests match these filters.";
      resultList.append(empty);
    }
    for (const row of rows) {
      const card = document.createElement("div");
      card.className = "result-row";
      const heading = document.createElement("strong");
      heading.textContent = `${row.alert_id} · ${row.requested_resource_type}`;
      const description = document.createElement("span");
      description.textContent = `${row.district} · ${row.allocated_quantity}/${row.requested_quantity} units · ${Number(row.straight_line_distance_km || 0).toFixed(1)} km proximity estimate`;
      card.append(heading, description);
      resultList.append(card);
    }
    if (allocations.length > rows.length) {
      const more = document.createElement("div");
      more.className = "subtle";
      more.textContent = `Showing ${rows.length} of ${allocations.length} allocation rows.`;
      resultList.append(more);
    }
    $("#method-notice").textContent = dispatchData.notice;
  }

  function setOptions(selector, label, values) {
    const select = $(selector);
    select.replaceChildren(new Option(label, label));
    for (const value of values.filter(Boolean).sort()) select.add(new Option(value, value));
  }

  async function loadDispatch() {
    dispatchSubmit.disabled = true;
    dispatchSubmit.textContent = "Calculating preview…";
    status("Preparing allocation preview…");
    try {
      const response = await fetch("/dispatch/preview", { headers: { Accept: "application/json" } });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail || `Preview failed (${response.status})`);
      dispatchData = payload;
      const rows = payload.requests;
      setOptions("#district-filter", "All districts", [...new Set(rows.map((row) => row.district))]);
      setOptions("#hazard-filter", "All hazards", [...new Set(rows.map((row) => row.hazard_type))]);
      setOptions("#resource-filter", "All resources", [...new Set(rows.map((row) => row.requested_resource_type))]);
      makeDispatchFeatures();
      $("#live-status").textContent = `${payload.summary.pending_requests} requests · preview ready`;
    } catch (error) {
      dispatchData = null;
      setFeatures([]);
      $("#inspector-title").textContent = "Preview unavailable";
      $("#inspector-copy").textContent = error instanceof Error ? error.message : String(error);
      $("#result-list").textContent = "Prepare allocation inputs and check that the inventory workbook is present.";
      $("#detail-stats").replaceChildren();
      setMetrics([["—", "Requests"], ["—", "Allocated units"], ["—", "Unfilled units"]]);
      status("Allocation preview could not be loaded.");
    } finally {
      dispatchSubmit.disabled = false;
      dispatchSubmit.textContent = "Generate allocation preview";
    }
  }

  function updateRouteMode() {
    const isRescue = mode.value === "rescue_dispatch";
    $("#rescue-fields").hidden = !isRescue;
    $("#evacuation-fields").hidden = isRescue;
    $("#facility-id").required = isRescue;
    $("#incident-id").required = isRescue;
    $("#scenario-id").required = !isRescue;
  }

  function showRouteResult(payload) {
    const result = payload.result || {};
    const features = [];
    const lines = [];
    const addLine = (geometry, props) => {
      const feature = routeFeature(geometry, props);
      if (feature) { features.push(feature); lines.push(feature); }
    };
    if (payload.route_type === "rescue_dispatch") {
      const route = result.route;
      addLine(route && route.geometry, { kind: "route", color: "#e86f65", label: "Rescue dispatch" });
      if (route && route.geometry && route.geometry.coordinates.length >= 2) {
        features.push(pointFeature(route.geometry.coordinates[0], { kind: "facility", label: "Dispatch facility" }));
        features.push(pointFeature(route.geometry.coordinates.at(-1), { kind: "incident", label: "Incident" }));
      }
    } else {
      for (const origin of result.origins || []) {
        for (const assignment of origin.assignments || []) {
          const geometry = assignment.route && assignment.route.geometry;
          addLine(geometry, { kind: "route", color: "#68c9c3", label: `${origin.origin_id} → ${assignment.shelter_name}` });
          if (geometry && geometry.coordinates.length >= 2) {
            features.push(pointFeature(geometry.coordinates[0], { kind: "origin", label: origin.origin_id }));
            features.push(pointFeature(geometry.coordinates.at(-1), { kind: "shelter", label: assignment.shelter_name }));
          }
        }
      }
    }
    setFeatures(features);
    const routeType = payload.route_type === "rescue_dispatch" ? "Rescue dispatch" : "Evacuation plan";
    $("#inspector-kicker").textContent = routeType;
    $("#inspector-title").textContent = result.status === "feasible" ? "Safe route found" : result.status === "partial" ? "Partial evacuation plan" : "No feasible route";
    $("#inspector-copy").textContent = `Scenario ${result.scenario_id || result.scenario?.scenario_id || "—"} · ${result.status || "unknown"}`;
    $("#list-title").textContent = "Route details";
    detailStats.replaceChildren();
    resultList.replaceChildren();
    if (payload.route_type === "rescue_dispatch") {
      textLine(detailStats, "Road travel time", result.road_network_travel_time_seconds == null ? "—" : `${Math.round(result.road_network_travel_time_seconds / 60)} min`);
      textLine(detailStats, "Network distance", result.route?.distance_meters == null ? "—" : `${(result.route.distance_meters / 1000).toFixed(1)} km`);
      textLine(detailStats, "Route edges", result.route?.edge_ids?.length ?? 0);
      if (result.reason) textLine(detailStats, "Outcome detail", result.reason);
      setMetrics([[result.status || "—", "Route status"], [lines.length, "Routes displayed"], [result.scenario_id || "—", "Scenario"]]);
    } else {
      const demand = result.demand || {};
      textLine(detailStats, "Evacuation origins", demand.origin_count ?? 0);
      textLine(detailStats, "People served", demand.served_people ?? 0);
      textLine(detailStats, "Known people unserved", demand.unserved_known_people ?? 0);
      textLine(detailStats, "Unknown demand origins", demand.unknown_demand_origin_count ?? 0);
      setMetrics([[result.status || "—", "Plan status"], [demand.served_people ?? 0, "People served"], [demand.unserved_known_people ?? 0, "Known people unserved"], [lines.length, "Routes displayed"]]);
    }
    const routeRows = payload.route_type === "rescue_dispatch"
      ? (result.route ? [{ title: "Facility → incident", detail: `${result.route.edge_ids?.length || 0} road segments` }] : [])
      : (result.origins || []).flatMap((origin) => (origin.assignments || []).map((assignment) => ({ title: `${origin.origin_id} → ${assignment.shelter_name}`, detail: `${assignment.people_assigned} people · ${(assignment.distance_meters / 1000).toFixed(1)} km` })));
    for (const item of routeRows.slice(0, 16)) {
      const card = document.createElement("div"); card.className = "result-row";
      const heading = document.createElement("strong"); heading.textContent = item.title;
      const description = document.createElement("span"); description.textContent = item.detail;
      card.append(heading, description); resultList.append(card);
    }
    if (!routeRows.length) resultList.textContent = result.reason || "No feasible route was returned.";
    $("#method-notice").textContent = "Hard-blocked roads are excluded. Scenario status reflects event-window evidence and is not a live road-closure feed.";
    status(lines.length ? `${lines.length} route(s) displayed.` : "No feasible route was returned.");
  }

  async function submitRoute(event) {
    event.preventDefault();
    const requestId = ++requestCounter;
    const values = new FormData(routeForm);
    const requestMode = String(values.get("mode"));
    const alertId = String(values.get("alert_id") || "").trim();
    const payload = requestMode === "rescue_dispatch"
      ? { mode: requestMode, facility_id: String(values.get("facility_id") || "").trim(), incident_record_id: String(values.get("incident_record_id") || "").trim() }
      : { mode: requestMode, scenario_id: String(values.get("scenario_id") || "").trim() };
    if (alertId) payload.alert_id = alertId;
    routeSubmit.disabled = true; routeSubmit.textContent = "Finding route…";
    status("Requesting route from the local API…");
    setFeatures([]);
    try {
      const response = await fetch("/route", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      const body = await response.json();
      if (requestId !== requestCounter) return;
      if (!response.ok) throw new Error(body.detail || `Routing request failed (${response.status})`);
      showRouteResult(body);
    } catch (error) {
      if (requestId === requestCounter) {
        $("#inspector-title").textContent = "Routing request failed";
        $("#inspector-copy").textContent = error instanceof Error ? error.message : String(error);
        $("#detail-stats").replaceChildren(); $("#result-list").textContent = "Check the scenario identifiers and local PostGIS connection.";
        status("No route displayed.");
      }
    } finally {
      if (requestId === requestCounter) { routeSubmit.disabled = false; routeSubmit.textContent = "Find safe route"; }
    }
  }

  function switchView(view) {
    activeView = view;
    document.querySelectorAll(".feature-tab").forEach((button) => button.setAttribute("aria-pressed", String(button.dataset.view === view)));
    const routing = view === "routing";
    $("#dispatch-controls").hidden = routing;
    $("#routing-controls").hidden = !routing;
    $("#feature-eyebrow").textContent = routing ? "Road-network planning" : "Allocation planning";
    $("#feature-title").textContent = routing ? "Hazard-aware dual routing" : "Resource-aware dispatch";
    $("#feature-intro").textContent = routing
      ? "Find rescue access routes or plan capacity-aware evacuation routes around blocked roads."
      : "Preview prioritized requests against available workbook inventory and review the proposed assignments.";
    $("#map-note").textContent = routing
      ? "Routes use the directed prototype road graph. Scenario edge status reflects event-window evidence, not live road conditions."
      : "Markers show alert and assigned resource locations. Distance values are straight-line proximity estimates, not road routes.";
    setFeatures([]);
    if (routing) {
      $("#inspector-kicker").textContent = "Routing";
      $("#inspector-title").textContent = "Route request";
      $("#inspector-copy").textContent = "Choose rescue dispatch or evacuation planning, then submit a scenario request.";
      $("#list-title").textContent = "Route results";
      $("#result-list").textContent = "No route requested yet.";
      $("#method-notice").textContent = "Flood and landslide intersections and active closed closures are hard blocks. Soft risk affects evacuation route cost.";
      detailStats.replaceChildren(); setMetrics([["2", "Routing modes"], ["—", "Scenario"]]);
    } else if (dispatchData) makeDispatchFeatures();
  }

  function initMap() {
    if (typeof maplibregl === "undefined") { status("Map library unavailable; controls can still be used."); return; }
    map = new maplibregl.Map({
      container: "map", center: [80.72, 7.87], zoom: 7,
      style: {
        version: 8,
        sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap contributors</a>" } },
        layers: [{ id: "osm-basemap", type: "raster", source: "osm", minzoom: 0, maxzoom: 19 }],
      },
      maxZoom: 18,
    });
    map.addControl(new maplibregl.NavigationControl(), "bottom-right");
    map.on("style.load", () => {
      map.addSource("results", { type: "geojson", data: { type: "FeatureCollection", features: [] } });
      map.addLayer({ id: "route-lines", type: "line", source: "results", filter: ["==", ["geometry-type"], "LineString"], paint: { "line-color": ["coalesce", ["get", "color"], "#65d3cc"], "line-width": 5, "line-opacity": .9 }, layout: { "line-cap": "round", "line-join": "round" } });
      map.addLayer({ id: "points", type: "circle", source: "results", filter: ["==", ["geometry-type"], "Point"], paint: {
        "circle-color": ["match", ["get", "kind"], "resource", "#e8be62", "facility", "#65d3cc", "shelter", "#78cf91", "incident", "#ef756b", "origin", "#65d3cc", "#63c9df"],
        "circle-radius": ["match", ["get", "kind"], "request", 6, 8], "circle-stroke-color": "#f5fafb", "circle-stroke-width": 1.5,
      } });
      map.on("click", "points", (event) => {
        const feature = event.features && event.features[0]; if (!feature) return;
        const props = feature.properties;
        const popup = document.createElement("div");
        const heading = document.createElement("strong"); heading.textContent = props.label || props.kind; popup.append(heading);
        const details = props.kind === "request"
          ? `${props.district || ""} · ${props.hazard || ""} · ${props.allocated}/${props.requested} allocated · ${props.unfilled} unfilled`
          : props.kind === "resource" ? `${props.district || ""} · ${props.quantity} units to ${props.alert}` : props.kind;
        const copy = document.createElement("div"); copy.textContent = details; popup.append(copy);
        new maplibregl.Popup().setLngLat(event.lngLat).setDOMContent(popup).addTo(map);
      });
      map.on("mouseenter", "points", () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "points", () => { map.getCanvas().style.cursor = ""; });
      sourcesReady = true;
      setFeatures(pendingFeatures);
      status("Map ready.", false);
      if (activeView === "dispatch" && dispatchData) makeDispatchFeatures();
    });
    map.on("error", (event) => { if (event.error) status("Basemap service error; local controls remain available."); });
  }

  document.querySelectorAll(".feature-tab").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  ["#district-filter", "#hazard-filter", "#resource-filter", "#show-requests", "#show-resources"].forEach((selector) => $(selector).addEventListener("change", () => { if (activeView === "dispatch" && dispatchData) makeDispatchFeatures(); }));
  dispatchSubmit.addEventListener("click", loadDispatch);
  $("#refresh").addEventListener("click", () => activeView === "dispatch" ? loadDispatch() : switchView("routing"));
  $("#clear-view").addEventListener("click", () => { setFeatures([]); status("Map cleared."); });
  routeForm.addEventListener("submit", submitRoute);
  mode.addEventListener("change", updateRouteMode);
  updateRouteMode();
  initMap();
  loadDispatch();
})();
