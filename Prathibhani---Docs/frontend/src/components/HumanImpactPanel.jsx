
import React from "react";

const impactColors = {
  "Very High": "#ef4444",
  High: "#f97316",
  Moderate: "#eab308",
  Low: "#22c55e",
};

function ImpactCard({ title, prediction }) {
  if (!prediction) {
    return (
      <div className="impact-card">
        <span className="impact-card-label">{title}</span>
        <p>No prediction available</p>
      </div>
    );
  }

  const color = impactColors[prediction.predicted_impact] || "#94a3b8";
  const probability = prediction.confidence * 100;

  return (
    <div className="impact-card">
      <span className="impact-card-label">{title}</span>

      <div className="impact-class" style={{ color }}>
        {prediction.predicted_impact}
      </div>

      <div className="impact-probability">
        <span>Predicted class probability</span>
        <strong>{probability.toFixed(1)}%</strong>
      </div>

      <div className="impact-progress-track">
        <div
          className="impact-progress-fill"
          style={{
            width: `${probability}%`,
            backgroundColor: color,
          }}
        />
      </div>

      <p className="impact-note">
        Experimental model estimate, not a verified disaster forecast.
      </p>
    </div>
  );
}

export default function HumanImpactPanel({ result }) {
  if (!result?.analysis) {
    return (
      <div className="human-impact-panel">
        <h2>Human Impact Analysis</h2>
        <p>Run a scenario to view the model predictions.</p>
      </div>
    );
  }

  const analysis = result.analysis;
  const humanExposure = result.human_exposure;
  const predictions = analysis.model_predictions || {};
  const priority = analysis.decision_priority || {};

  const population =
    predictions.flood?.shap_explanation?.find(
      (item) => item.feature === "total_population"
    )?.feature_value ??
    predictions.landslide?.shap_explanation?.find(
      (item) => item.feature === "total_population"
    )?.feature_value;

  return (
    <section className="human-impact-panel">
      <div className="impact-panel-heading">
        <div>
          <h2>Human Impact Analysis</h2>
          <p>
            {analysis.division} DS Division, {analysis.district} District
          </p>
        </div>

        <span className="impact-research-badge">
          Research Scenario
        </span>
      </div>

      <div className="impact-cards-grid">
        <ImpactCard
          title="Flood Human Impact"
          prediction={predictions.flood}
        />

        <ImpactCard
          title="Landslide Human Impact"
          prediction={predictions.landslide}
        />
      </div>

      <div className="impact-summary-grid">
        <div className="impact-summary-card">
          <span>Decision Priority</span>
          <strong
            style={{
              color: impactColors[priority.priority_level] || "#fff",
            }}
          >
            {priority.priority_level || "Unavailable"}
          </strong>
          <small>
            Provisional score:{" "}
            {typeof priority.priority_score === "number"
              ? priority.priority_score.toFixed(3)
              : "N/A"}
          </small>
        </div>

        <div className="impact-summary-card">
          <span>Historical DS Population</span>
          <strong>
            {typeof population === "number"
              ? population.toLocaleString()
              : "Unavailable"}
          </strong>
          <small>Total population, not exposed population</small>
        </div>

        <div className="impact-summary-card">
          <span>Potentially Exposed Population</span>
          <strong>
            {humanExposure
              ? humanExposure.potentially_exposed_population.toLocaleString()
              : "Not estimated"}
          </strong>
          <small>
            {humanExposure
              ? `Illustrative scenario: ${(
                  humanExposure.scenario_exposed_fraction * 100
                ).toFixed(0)}% of DS population`
              : "No population exposure scenario provided"}
          </small>
        </div>

        {humanExposure && (
          <>
            <div className="impact-summary-card">
              <span>Potentially Exposed Children (0–14)</span>
              <strong>
                {humanExposure.potentially_exposed_children_0_14.toLocaleString()}
              </strong>
              <small>Scenario estimate using 2024 census age distribution</small>
            </div>

            <div className="impact-summary-card">
              <span>Potentially Exposed Older Adults (60+)</span>
              <strong>
                {humanExposure.potentially_exposed_elderly_60_plus.toLocaleString()}
              </strong>
              <small>Scenario estimate using 2024 census age distribution</small>
            </div>
          </>
        )}
      </div>

      <p className="impact-disclaimer">
        Research demonstration only. The ML models use demographic
        features to predict historical impact classes. Scenario hazard
        severity affects decision scoring, not the ML classifications.
        Population exposure figures are illustrative scenario estimates,
        not observed affected-person counts or verified hazard footprints.
        These outputs are not official warnings.
      </p>
    </section>
  );
}
