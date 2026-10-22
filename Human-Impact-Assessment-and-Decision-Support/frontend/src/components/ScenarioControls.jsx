
import React from "react";
import { SlidersHorizontal, Play } from "lucide-react";

function ScenarioSlider({
  label,
  value,
  onChange,
  description,
  disabled = false,
  percentage = false,
}) {
  return (
    <div className="scenario-slider">
      <div className="scenario-slider-heading">
        <label>{label}</label>
        <strong>
          {percentage
            ? `${Math.round(value * 100)}%`
            : value.toFixed(2)}
        </strong>
      </div>

      <input
        type="range"
        min="0"
        max="1"
        step="0.05"
        value={value}
        disabled={disabled}
        onChange={(event) =>
          onChange(Number(event.target.value))
        }
      />

      <small>{description}</small>
    </div>
  );
}

export default function ScenarioControls({
  location,
  scenario,
  onScenarioChange,
  onAnalyze,
  loading,
}) {
  function updateField(field, value) {
    onScenarioChange({
      ...scenario,
      [field]: value,
    });
  }

  return (
    <section className="scenario-controls">
      <div className="scenario-controls-heading">
        <div>
          <h2>
            <SlidersHorizontal size={20} />
            Hazard Scenario Configuration
          </h2>

          <p>
            {location.division} DS Division,{" "}
            {location.district} District
          </p>
        </div>

        <span className="scenario-mode-badge">
          Manual Research Scenario
        </span>
      </div>

      <div className="scenario-slider-grid">
        <ScenarioSlider
          label="Flood Severity"
          value={scenario.floodSeverity}
          onChange={(value) =>
            updateField("floodSeverity", value)
          }
          description="Assumed flood severity (0–1)"
        />

        <ScenarioSlider
          label="Landslide Severity"
          value={scenario.landslideSeverity}
          onChange={(value) =>
            updateField("landslideSeverity", value)
          }
          description="Assumed landslide severity (0–1)"
        />

        <ScenarioSlider
          label="Exposure"
          value={scenario.exposure}
          onChange={(value) =>
            updateField("exposure", value)
          }
          description="Assumed exposure factor (0–1)"
        />

        <ScenarioSlider
          label="Assumed Population Exposure"
          value={scenario.exposedFraction}
          onChange={(value) =>
            updateField("exposedFraction", value)
          }
          percentage
          description="Illustrative percentage of DS residents exposed (0–100%). Not measured from a hazard footprint."
        />

        <ScenarioSlider
          label="Sensitivity"
          value={scenario.sensitivity}
          onChange={(value) =>
            updateField("sensitivity", value)
          }
          description="Assumed vulnerability/sensitivity factor (0–1)"
        />

        <ScenarioSlider
          label="Response Capacity"
          value={scenario.responseCapacity}
          onChange={(value) =>
            updateField("responseCapacity", value)
          }
          description="Assumed response capacity (0–1); higher reduces priority"
        />
      </div>

      <div className="scenario-controls-footer">
        <p>
          These are provisional scenario inputs, not live
          measurements. Hazard severity changes the decision
          priority score, not the demographic ML predictions.
        </p>

        <button
          type="button"
          className="scenario-run-button"
          onClick={onAnalyze}
          disabled={loading}
        >
          <Play size={16} />
          {loading ? "Analyzing..." : "Run Scenario Analysis"}
        </button>
      </div>
    </section>
  );
}
