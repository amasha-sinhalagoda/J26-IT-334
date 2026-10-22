
const API_BASE_URL = "http://127.0.0.1:8000";

export async function analyzeHazardScenario({
  district,
  division,
  floodSeverity,
  landslideSeverity,
  exposure = 0.7,
  sensitivity = 0.65,
  responseCapacity = 0.4,
  exposedFraction = 0.10,
}) {
  const response = await fetch(`${API_BASE_URL}/api/analyze`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      district,
      division,
      flood_severity: floodSeverity,
      landslide_severity: landslideSeverity,
      exposure,
      sensitivity,
      response_capacity: responseCapacity,
      exposed_fraction: exposedFraction,
      include_example_infrastructure: false,
    }),
  });

  if (!response.ok) {
    let message = `Analysis failed (HTTP ${response.status})`;

    try {
      const errorData = await response.json();

      if (typeof errorData.detail === "string") {
        message = errorData.detail;
      } else if (Array.isArray(errorData.detail)) {
        message = errorData.detail
          .map((item) => item.msg)
          .join("; ");
      }
    } catch {
      // Keep the HTTP status message if the response is not JSON.
    }

    throw new Error(message);
  }

  return response.json();
}
