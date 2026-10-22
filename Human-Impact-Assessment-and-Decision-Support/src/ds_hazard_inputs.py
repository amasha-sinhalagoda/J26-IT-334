
from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timezone


@dataclass
class DSHazardInput:
    district: str
    division: str
    flood_severity: Optional[float] = None
    landslide_severity: Optional[float] = None
    source: str = "manual_scenario"
    reference_time: Optional[str] = None


def validate_hazard_input(data: DSHazardInput):

    if not data.district.strip():
        raise ValueError("District is required.")

    if not data.division.strip():
        raise ValueError("DS division is required.")

    if (
        data.flood_severity is None
        and data.landslide_severity is None
    ):
        raise ValueError(
            "At least one hazard severity is required."
        )

    for name in ["flood_severity", "landslide_severity"]:
        value = getattr(data, name)

        if value is not None:
            if not 0 <= value <= 1:
                raise ValueError(
                    f"{name} must be between 0 and 1."
                )

    return True


def prepare_hazard_input(data: DSHazardInput):

    validate_hazard_input(data)

    return {
        "district": data.district.strip(),
        "division": data.division.strip(),
        "flood_severity": data.flood_severity,
        "landslide_severity": data.landslide_severity,
        "hazard_source": data.source,
        "reference_time": data.reference_time,
        "processed_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "scenario_type": (
            "Provisional research demonstration"
        ),
        "operational_warning": False,
    }


if __name__ == "__main__":

    example = DSHazardInput(
        district="Colombo",
        division="Kaduwela",
        flood_severity=0.8,
        landslide_severity=0.6,
        source="manual_scenario",
    )

    result = prepare_hazard_input(example)

    print("\nDS-LEVEL HAZARD INPUT")
    print("=====================")

    for key, value in result.items():
        print(f"{key}: {value}")
