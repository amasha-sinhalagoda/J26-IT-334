
import React from "react";
import {
  AlertTriangle,
  ClipboardCheck,
  ShieldAlert,
  BellOff,
  MapPin,
  CheckCircle2,
} from "lucide-react";

export default function ImmediateActionsPanel({ result }) {
  if (!result?.analysis || !result?.decision_support) {
    return (
      <section className="immediate-actions-panel">
        <h2>Immediate Decision Support</h2>
        <p>Run a hazard scenario to view recommended actions.</p>
      </section>
    );
  }

  const analysis = result.analysis;
  const decision = result.decision_support;
  const priority = analysis.decision_priority || {};
  const recommendations = decision.recommendations || [];

  const activeHazards = Object.keys(
    analysis.model_predictions || {}
  );

  return (
    <section className="immediate-actions-panel">
      <div className="actions-heading">
        <div>
          <h2>
            <ShieldAlert size={21} />
            Immediate Decision Support
          </h2>
          <p>
            Scenario-based response guidance for {analysis.division},{" "}
            {analysis.district}
          </p>
        </div>

        <span className="actions-research-label">
          Research Advisory
        </span>
      </div>

      <div className="actions-status-grid">
        <div className="actions-status-card">
          <span>Decision Priority</span>
          <strong className="actions-priority">
            {priority.priority_level || "Unavailable"}
          </strong>
          <small>
            Provisional score:{" "}
            {typeof priority.priority_score === "number"
              ? priority.priority_score.toFixed(3)
              : "N/A"}
          </small>
        </div>

        <div className="actions-status-card">
          <span>Alert Grade</span>
          <strong className="actions-alert-grade">
            {decision.alert_grade || "Not assigned"}
          </strong>
          <small>For research review only</small>
        </div>

        <div className="actions-status-card">
          <span>Hazards Assessed</span>
          <strong>
            {activeHazards.length
              ? activeHazards
                  .map(
                    (hazard) =>
                      hazard.charAt(0).toUpperCase() +
                      hazard.slice(1)
                  )
                  .join(" + ")
              : "None"}
          </strong>
          <small>
            {priority.overlapping_hazards
              ? "Combined-hazard scenario"
              : "Single-hazard scenario"}
          </small>
        </div>
      </div>

      <div className="actions-alert-box">
        <div className="actions-alert-title">
          <AlertTriangle size={19} />
          <strong>Provisional Decision Advisory</strong>
        </div>

        <p>
          {decision.alert_message ||
            "No advisory message is available."}
        </p>
      </div>

      <div className="actions-recommendations">
        <h3>
          <ClipboardCheck size={19} />
          Recommended Immediate Review Actions
        </h3>

        {recommendations.length > 0 ? (
          <div className="actions-list">
            {recommendations.map((recommendation, index) => (
              <div className="actions-item" key={index}>
                <div className="actions-item-number">
                  {index + 1}
                </div>
                <p>{recommendation}</p>
              </div>
            ))}
          </div>
        ) : (
          <p>No recommendations were generated.</p>
        )}
      </div>

      <div className="actions-footer-grid">
        <div className="actions-footer-item">
          <MapPin size={17} />
          <div>
            <strong>Infrastructure Assessment</strong>
            <span>
              {decision.critical_infrastructure_count ?? 0}{" "}
              critical assets flagged in supplied data
            </span>
          </div>
        </div>

        <div className="actions-footer-item">
          {decision.notification_sent ? (
            <CheckCircle2 size={17} />
          ) : (
            <BellOff size={17} />
          )}
          <div>
            <strong>Notification Status</strong>
            <span>
              {decision.notification_sent
                ? "Notification reported as sent"
                : "No notification sent"}
            </span>
          </div>
        </div>
      </div>

      
    </section>
  );
}
