from pathlib import Path
import pandas as pd

BASE = Path(__file__).resolve().parents[1]
DATA_PATH = BASE / "data/processed/ds_population_summary.csv"


def normalize_name(value):
    return " ".join(str(value).strip().casefold().split())


def assess_human_exposure(
    district,
    division,
    exposed_fraction,
):
    """
    Scenario-based population exposure assessment.

    exposed_fraction is an explicit scenario assumption
    between 0 and 1, NOT a prediction from hazard severity.

    Assumes exposed people have the same age distribution
    as the overall DS Division.
    """

    if not 0 <= exposed_fraction <= 1:
        raise ValueError(
            "exposed_fraction must be between 0 and 1."
        )

    df = pd.read_csv(DATA_PATH)

    matched = df[
        df["district"].map(normalize_name).eq(
            normalize_name(district)
        )
        &
        df["ds_division"].map(normalize_name).eq(
            normalize_name(division)
        )
    ]

    if len(matched) != 1:
        raise ValueError(
            f"Expected one census match for "
            f"{division}, {district}; found {len(matched)}."
        )

    row = matched.iloc[0]

    population = int(row["population"])
    children = int(row["children_0_14"])
    elderly = int(row["elderly_60_plus"])

    return {
        "district": str(row["district"]),
        "division": str(row["ds_division"]),
        "census_year": 2024,
        "total_population": population,
        "total_children_0_14": children,
        "total_elderly_60_plus": elderly,
        "scenario_exposed_fraction": exposed_fraction,
        "potentially_exposed_population": round(
            population * exposed_fraction
        ),
        "potentially_exposed_children_0_14": round(
            children * exposed_fraction
        ),
        "potentially_exposed_elderly_60_plus": round(
            elderly * exposed_fraction
        ),
        "assessment_type": "scenario_based_exposure",
        "verified_hazard_footprint": False,
        "operational_warning": False,
        "limitations": (
            "Exposure fraction is a scenario assumption, "
            "not a measured or predicted disaster footprint. "
            "Age-specific estimates assume uniform exposure "
            "across the DS Division. These are not observed "
            "affected-person counts."
        ),
    }


if __name__ == "__main__":
    result = assess_human_exposure(
        district="Colombo",
        division="Kaduwela",
        exposed_fraction=0.10,
    )

    for key, value in result.items():
        print(f"{key}: {value}")
