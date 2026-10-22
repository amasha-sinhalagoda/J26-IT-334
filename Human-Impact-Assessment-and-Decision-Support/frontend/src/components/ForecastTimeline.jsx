
import React, { useState } from "react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
} from "recharts";
import { Clock3, Info, TrendingUp } from "lucide-react";

const demoForecast = [
  { hour: 0, flood: 0.30, landslide: 0.20 },
  { hour: 6, flood: 0.42, landslide: 0.25 },
  { hour: 12, flood: 0.58, landslide: 0.35 },
  { hour: 18, flood: 0.74, landslide: 0.48 },
  { hour: 24, flood: 0.65, landslide: 0.56 },
  { hour: 30, flood: 0.48, landslide: 0.46 },
  { hour: 36, flood: 0.35, landslide: 0.38 },
];

const horizonOptions = [12, 24, 36];

export default function ForecastTimeline() {
  const [horizon, setHorizon] = useState(36);

  const visibleForecast = demoForecast.filter(
    (item) => item.hour <= horizon
  );

  const maxFlood = Math.max(
    ...visibleForecast.map((item) => item.flood)
  );

  const maxLandslide = Math.max(
    ...visibleForecast.map((item) => item.landslide)
  );

  return (
    <section className="forecast-timeline-panel">
      <div className="forecast-header">
        <div>
          <h2>
            <Clock3 size={22} />
            Multi-Hazard Forecast Timeline
          </h2>

          <p>
            Illustrative flood and landslide severity trends
          </p>
        </div>

        <span className="forecast-demo-badge">
          Synthetic Demonstration Data
        </span>
      </div>

      <div className="forecast-horizon">
        <span>Forecast horizon</span>

        <div className="forecast-horizon-buttons">
          {horizonOptions.map((option) => (
            <button
              key={option}
              type="button"
              className={
                horizon === option ? "active" : ""
              }
              onClick={() => setHorizon(option)}
            >
              {option} hours
            </button>
          ))}
        </div>
      </div>

      <div className="forecast-chart-card">
        <ResponsiveContainer width="100%" height={350}>
          <LineChart
            data={visibleForecast}
            margin={{
              top: 15,
              right: 25,
              left: 0,
              bottom: 10,
            }}
          >
            <CartesianGrid
              stroke="#334155"
              strokeDasharray="3 3"
            />

            <XAxis
              dataKey="hour"
              tick={{ fill: "#94a3b8", fontSize: 12 }}
              tickFormatter={(value) => `${value}h`}
            />

            <YAxis
              domain={[0, 1]}
              tick={{ fill: "#94a3b8", fontSize: 12 }}
            />

            <Tooltip
              formatter={(value) =>
                Number(value).toFixed(2)
              }
              labelFormatter={(hour) =>
                `T + ${hour} hours`
              }
              contentStyle={{
                background: "#172a46",
                border: "1px solid #315078",
                borderRadius: "8px",
                color: "#f8fafc",
              }}
            />

            <Legend />

            <Line
              type="monotone"
              dataKey="flood"
              name="Flood severity"
              stroke="#38bdf8"
              strokeWidth={3}
              dot={{ r: 4 }}
              activeDot={{ r: 6 }}
            />

            <Line
              type="monotone"
              dataKey="landslide"
              name="Landslide severity"
              stroke="#f59e0b"
              strokeWidth={3}
              dot={{ r: 4 }}
              activeDot={{ r: 6 }}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>

      <div className="forecast-summary-grid">
        <div className="forecast-summary-card">
          <TrendingUp size={20} />

          <p>Maximum Illustrative Flood Severity</p>

          <strong>{maxFlood.toFixed(2)}</strong>
        </div>

        <div className="forecast-summary-card">
          <TrendingUp size={20} />

          <p>Maximum Illustrative Landslide Severity</p>

          <strong>{maxLandslide.toFixed(2)}</strong>
        </div>
      </div>

    
    </section>
  );
}
