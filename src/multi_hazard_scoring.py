from dataclasses import dataclass
from typing import Optional


@dataclass
class HazardInput:
    flood_severity: Optional[float]
    landslide_severity: Optional[float]
    exposure: float
    sensitivity: float
    response_capacity: float


def validate_score(name, value):
    if value is not None and not 0 <= value <= 1:
        raise ValueError(
            f"{name} must be between 0 and 1"
        )


def calculate_priority(data: HazardInput):

    for name in [
        "flood_severity",
        "landslide_severity",
        "exposure",
        "sensitivity",
        "response_capacity",
    ]:
        validate_score(name, getattr(data, name))

    severities = [
        value
        for value in [
            data.flood_severity,
            data.landslide_severity,
        ]
        if value is not None
    ]

    if not severities:
        raise ValueError(
            "At least one hazard severity is required."
        )

    # Highest hazard severity forms the base.
    hazard_score = max(severities)

    # Provisional overlap adjustment when both
    # hazards have nonzero severity.
    overlap = (
        len(severities) == 2
        and all(value > 0 for value in severities)
    )

    overlap_adjustment = 0.10 if overlap else 0.0

    adjusted_hazard = min(
        1.0,
        hazard_score + overlap_adjustment
    )

    # Provisional weighted decision score.
    priority_score = (
        0.40 * adjusted_hazard
        + 0.25 * data.exposure
        + 0.20 * data.sensitivity
        + 0.15 * (1 - data.response_capacity)
    )

    if priority_score >= 0.75:
        priority_level = "Very High"
    elif priority_score >= 0.55:
        priority_level = "High"
    elif priority_score >= 0.35:
        priority_level = "Moderate"
    else:
        priority_level = "Low"

    return {
        "hazard_score": round(hazard_score, 4),
        "overlapping_hazards": overlap,
        "adjusted_hazard_score": round(
            adjusted_hazard, 4
        ),
        "priority_score": round(priority_score, 4),
        "priority_level": priority_level,
        "score_components": {
            "hazard": round(
                0.40 * adjusted_hazard, 4
            ),
            "exposure": round(
                0.25 * data.exposure, 4
            ),
            "sensitivity": round(
                0.20 * data.sensitivity, 4
            ),
            "limited_response_capacity": round(
                0.15 * (1 - data.response_capacity), 4
            ),
        },
        "scenario_type": "Provisional demonstration",
        "operational_warning": False,
    }


if __name__ == "__main__":

    sample = HazardInput(
        flood_severity=0.8,
        landslide_severity=0.6,
        exposure=0.7,
        sensitivity=0.65,
        response_capacity=0.4,
    )

    result = calculate_priority(sample)

    for key, value in result.items():
        print(f"{key}: {value}")