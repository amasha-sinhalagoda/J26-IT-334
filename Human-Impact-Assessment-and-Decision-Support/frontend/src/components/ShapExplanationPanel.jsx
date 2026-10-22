
import React from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Cell,
  ReferenceLine,
} from "recharts";
import { BrainCircuit, Info } from "lucide-react";

const COLORS = {
  positive: "#f87171",
  negative: "#60a5fa",
};

function ShapChart({ title, prediction }) {
  if (!prediction) {
    return (
      <div className="shap-chart-card">
        <h3>{title}</h3>
        <p>No model prediction available.</p>
      </div>
    );
  }

  const shapValues = prediction.shap_explanation || [];

  const chartData = shapValues
    .map((item) => ({
      feature: item.feature_name || item.feature,
      contribution: Number(item.shap_value) || 0,
    }))
    .sort(
      (a, b) =>
        Math.abs(b.contribution) - Math.abs(a.contribution)
    );

  const maxMagnitude = Math.max(
    0.01,
    ...chartData.map((item) => Math.abs(item.contribution))
  );

  const axisLimit = Math.ceil(maxMagnitude * 100) / 100;

  return (
    <div className="shap-chart-card">
      <div className="shap-chart-heading">
        <div>
          <h3>{title}</h3>
          <p>
            Predicted class:{" "}
            <strong>{prediction.predicted_impact}</strong>
          </p>
        </div>

        <span className="shap-probability">
          {(prediction.confidence * 100).toFixed(1)}%
        </span>
      </div>

      {chartData.length > 0 ? (
        <>
          <div className="shap-chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={chartData}
                layout="vertical"
                margin={{
                  top: 10,
                  right: 22,
                  left: 16,
                  bottom: 10,
                }}
              >
                <CartesianGrid
                  stroke="#334155"
                  strokeDasharray="3 3"
                  horizontal={false}
                />

                <XAxis
                  type="number"
                  domain={[-axisLimit, axisLimit]}
                  tick={{ fill: "#94a3b8", fontSize: 11 }}
                  tickFormatter={(value) => value.toFixed(2)}
                />

                <YAxis
                  type="category"
                  dataKey="feature"
                  width={155}
                  tick={{ fill: "#cbd5e1", fontSize: 11 }}
                  interval={0}
                />

                <Tooltip
                  formatter={(value) => [
                    Number(value).toFixed(4),
                    "SHAP contribution",
                  ]}
                  contentStyle={{
                    background: "#172a46",
                    border: "1px solid #315078",
                    borderRadius: "8px",
                    color: "#f8fafc",
                  }}
                  labelStyle={{ color: "#f8fafc" }}
                />

                <ReferenceLine
                  x={0}
                  stroke="#e2e8f0"
                  strokeWidth={1}
                />

                <Bar
                  dataKey="contribution"
                  barSize={17}
                  radius={[3, 3, 3, 3]}
                >
                  {chartData.map((item, index) => (
                    <Cell
                      key={index}
                      fill={
                        item.contribution >= 0
                          ? COLORS.positive
                          : COLORS.negative
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <div className="shap-legend">
            <span>
              <i className="shap-legend-positive" />
              Positive contribution
            </span>

            <span>
              <i className="shap-legend-negative" />
              Negative contribution
            </span>
          </div>
        </>
      ) : (
        <p>SHAP explanation is unavailable.</p>
      )}
    </div>
  );
}

export default function ShapExplanationPanel({ result }) {
  const predictions = result?.analysis?.model_predictions;

  if (!predictions) {
    return (
      <section className="shap-explanation-panel">
        <h2>Explainable AI Analysis</h2>
        <p>Run an analysis to view SHAP explanations.</p>
      </section>
    );
  }

  return (
    <section className="shap-explanation-panel">
      <div className="shap-panel-heading">
        <div>
          <h2>
            <BrainCircuit size={22} />
            Explainable AI — SHAP Analysis
          </h2>
          <p>
            Demographic feature contributions to experimental
            human-impact classifications
          </p>
        </div>
      </div>

      <div className="shap-charts-grid">
        <ShapChart
          title="Flood Model Explanation"
          prediction={predictions.flood}
        />

        <ShapChart
          title="Landslide Model Explanation"
          prediction={predictions.landslide}
        />
      </div>

      <div className="shap-information">
        <Info size={19} />

        <div>
          <strong>How to interpret these charts</strong>

          <p>
            Red bars show positive SHAP contributions to the
            model output being explained, while blue bars show
            negative contributions. Larger absolute values
            indicate stronger feature influence in this
            individual prediction.
          </p>

          <p>
            These explanations concern the demographic
            features used by the experimental classifiers.
            They do not establish causation or explain rainfall,
            soil conditions, or real-time hazard severity.
            SHAP values must be interpreted in the output
            scale used by the model explainer.
          </p>
        </div>
      </div>
    </section>
  );
}
