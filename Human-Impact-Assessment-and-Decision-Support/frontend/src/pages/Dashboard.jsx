
import React, { useRef, useState } from "react";

import Sidebar from "../components/Sidebar";
import RiskMap from "../components/RiskMap";
import HumanImpactPanel from "../components/HumanImpactPanel";
import ImmediateActionsPanel from "../components/ImmediateActionsPanel";
import ShapExplanationPanel from "../components/ShapExplanationPanel";
import ScenarioControls from "../components/ScenarioControls";
import SafetyPlacesPanel from "../components/SafetyPlacesPanel";
import ForecastTimeline from "../components/ForecastTimeline";

import { analyzeHazardScenario } from "../services/api";

import "../styles/dashboard.css";

const pageTitles = {
  overview: "Overview Dashboard",
  gis: "GIS Risk Map",
  "human-impact": "Human Impact Analysis",
  "ml-analysis": "Explainable AI Analysis",
  decisions: "Immediate Decision Support",
  safety: "Safety Locations",
  timeline: "Forecast Timeline",
};

const initialScenario = {
  floodSeverity: 0.8,
  landslideSeverity: 0.6,
  exposure: 0.7,
  exposedFraction: 0.10,
  sensitivity: 0.65,
  responseCapacity: 0.4,
};

export default function Dashboard() {
  // Sidebar navigation
  const [activePage, setActivePage] = useState("overview");

  // Selected DS Division from the GIS map
  const [selectedLocation, setSelectedLocation] = useState({
    district: "Colombo",
    division: "Kaduwela",
  });

  // User-configurable research scenario
  const [scenario, setScenario] = useState(initialScenario);

  // FastAPI analysis state
  const [analysisResult, setAnalysisResult] = useState(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisError, setAnalysisError] = useState("");

  // Track which location produced the displayed results
  const [analyzedLocation, setAnalyzedLocation] = useState(null);

  // Prevent outdated API responses from replacing newer results
  const requestVersion = useRef(0);

  function clearAnalysis() {
    requestVersion.current += 1;
    setAnalysisResult(null);
    setAnalyzedLocation(null);
    setAnalysisError("");
    setAnalysisLoading(false);
  }

  // Called when the user clicks a DS Division on the map
  function handleDivisionSelection(location) {
    if (!location?.district || !location?.division) {
      return;
    }

    setSelectedLocation({
      district: location.district,
      division: location.division,
    });

    // Old analysis results must not appear under a new location
    clearAnalysis();
  }

  // Called when the user changes a scenario slider
  function handleScenarioChange(nextScenario) {
    setScenario(nextScenario);

    // The displayed results no longer match the scenario inputs
    clearAnalysis();
  }

  // Send selected location and scenario values to FastAPI
  async function runScenarioAnalysis() {
    const currentRequest = ++requestVersion.current;

    const location = { ...selectedLocation };
    const scenarioInputs = { ...scenario };

    setAnalysisLoading(true);
    setAnalysisError("");
    setAnalysisResult(null);
    setAnalyzedLocation(null);

    try {
      const result = await analyzeHazardScenario({
        district: location.district,
        division: location.division,
        floodSeverity: scenarioInputs.floodSeverity,
        landslideSeverity: scenarioInputs.landslideSeverity,
        exposure: scenarioInputs.exposure,
        exposedFraction: scenarioInputs.exposedFraction,
        sensitivity: scenarioInputs.sensitivity,
        responseCapacity: scenarioInputs.responseCapacity,
      });

      // Ignore an old response if the user changed the location
      // or scenario while the request was running.
      if (currentRequest !== requestVersion.current) {
        return;
      }

      setAnalysisResult(result);
      setAnalyzedLocation(location);
    } catch (error) {
      if (currentRequest !== requestVersion.current) {
        return;
      }

      setAnalysisError(
        error.message || "Unable to complete the analysis."
      );
    } finally {
      if (currentRequest === requestVersion.current) {
        setAnalysisLoading(false);
      }
    }
  }

  // Which sections should appear on each sidebar page?
  const showMap =
    activePage === "overview" ||
    activePage === "gis";

  const showHumanImpact =
    activePage === "overview" ||
    activePage === "human-impact";

  const showDecisions =
    activePage === "overview" ||
    activePage === "decisions";

  const showShap =
    activePage === "overview" ||
    activePage === "ml-analysis";

  const showScenarioControls = [
    "overview",
    "gis",
    "human-impact",
    "ml-analysis",
    "decisions",
  ].includes(activePage);

  return (
    <div className="dashboard-layout">
      {/* LEFT SIDEBAR */}
      <Sidebar
        activePage={activePage}
        onNavigate={setActivePage}
      />

      {/* MAIN DASHBOARD */}
      <main className="dashboard-main">
        <header className="dashboard-header">
          <div>
            <h1>
              {pageTitles[activePage] || "Dashboard"}
            </h1>

            <p>
              Multi-Hazard Human Impact & Decision Support System
            </p>
          </div>
        </header>

        <section className="dashboard-content">

          {/* INTERACTIVE SCENARIO CONFIGURATION */}
          {showScenarioControls && (
            <>
              <ScenarioControls
                location={selectedLocation}
                scenario={scenario}
                onScenarioChange={handleScenarioChange}
                onAnalyze={runScenarioAnalysis}
                loading={analysisLoading}
              />

              {/* API ERROR MESSAGE */}
              {analysisError && (
                <div
                  className="api-test-panel"
                  role="alert"
                >
                  <h3>Analysis Unavailable</h3>

                  <p className="api-test-error">
                    {analysisError}
                  </p>

                  <p>
                    Check that FastAPI is running and that
                    demographic data exists for the selected
                    DS Division.
                  </p>
                </div>
              )}

              {/* SUCCESS MESSAGE */}
              {analysisResult && analyzedLocation && (
                <div className="api-test-results">
                  <h3>Scenario Analysis Completed</h3>

                  <p>
                    <strong>Selected location:</strong>{" "}
                    {analyzedLocation.division},{" "}
                    {analyzedLocation.district}
                  </p>

                  <p>
                    <strong>Decision priority:</strong>{" "}
                    {analysisResult.analysis.decision_priority
                      .priority_level}
                  </p>

                  <p>
                    <strong>Priority score:</strong>{" "}
                    {analysisResult.analysis.decision_priority
                      .priority_score.toFixed(3)}
                  </p>

                  <p className="api-test-disclaimer">
                    Research demonstration only — not an
                    official disaster warning.
                  </p>
                </div>
              )}
            </>
          )}

          {/* GIS MAP */}
          {showMap && (
            <RiskMap
              onSelectDivision={handleDivisionSelection}
            />
          )}

          {/* HUMAN IMPACT ANALYSIS */}
          {showHumanImpact && (
            <HumanImpactPanel result={analysisResult} />
          )}

          {/* IMMEDIATE DECISION SUPPORT */}
          {showDecisions && (
            <ImmediateActionsPanel result={analysisResult} />
          )}

          {/* EXPLAINABLE AI / SHAP */}
          {showShap && (
            <ShapExplanationPanel result={analysisResult} />
          )}

          {/* SAFETY LOCATIONS */}
          {activePage === "safety" && <SafetyPlacesPanel />}

          
          {/* RESEARCH DISCLAIMER */}
          <p
            style={{
              color: "#fbbf24",
              fontSize: "12px",
              lineHeight: 1.7,
              marginTop: "20px",
            }}
          >
            Research demonstration only. Hazard inputs and exposure
            estimates are simulated or provisional. Machine learning
            predictions are experimental. This dashboard does not issue
            official disaster warnings, evacuation orders, or emergency
            notifications.
          </p>

          {/* FORECAST TIMELINE */}
          {activePage === "timeline" && <ForecastTimeline />}
        

        </section>
      </main>
    </div>
  );
}
