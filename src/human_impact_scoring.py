
import numpy as np
import pandas as pd


def normalize_population(values):
    """Scale population using a fixed illustrative reference."""
    values = pd.to_numeric(values, errors="coerce")

    # 100,000 is a provisional reference, not a validated threshold.
    return (values / 100000).clip(0, 1)


def calculate_human_impact_priority(
    data,
    hazard_column="hazard_severity"
):
    """
    Calculate illustrative DS-level risk priority scores.

    Hazard severity must be a value from 0 to 1.
    This is a decision-support score, not an ML prediction.
    """

    df = data.copy()

    required = [
        hazard_column,
        "total_population",
        "children_0_14_ratio",
        "elderly_60_plus_ratio",
        "unprotected_well_ratio",
        "no_toilet_ratio",
        "public_toilet_ratio"
    ]

    missing = [
        column for column in required
        if column not in df.columns
    ]

    if missing:
        raise ValueError(f"Missing columns: {missing}")

    numeric = df[required].apply(
        pd.to_numeric,
        errors="coerce"
    )

    if numeric.isna().any().any():
        raise ValueError(
            "Missing or nonnumeric scoring values detected."
        )

    if not numeric[hazard_column].between(0, 1).all():
        raise ValueError(
            "Hazard severity must be between 0 and 1."
        )

    ratio_columns = [
        "children_0_14_ratio",
        "elderly_60_plus_ratio",
        "unprotected_well_ratio",
        "no_toilet_ratio",
        "public_toilet_ratio"
    ]

    if not numeric[ratio_columns].ge(0).all().all():
        raise ValueError("Negative vulnerability ratios detected.")

    # Support ratios stored either as fractions or percentages.
    if numeric[ratio_columns].max().max() > 1:
        raise ValueError(
            "Vulnerability ratios must be fractions from 0 to 1."
        )

    df["hazard_score"] = numeric[hazard_column]

    df["exposure_score"] = normalize_population(
        numeric["total_population"]
    )

    df["sensitivity_score"] = (
        0.30 * numeric["children_0_14_ratio"]
        + 0.30 * numeric["elderly_60_plus_ratio"]
        + 0.15 * numeric["unprotected_well_ratio"]
        + 0.15 * numeric["no_toilet_ratio"]
        + 0.10 * numeric["public_toilet_ratio"]
    ).clip(0, 1)

    df["priority_score"] = (
        0.40 * df["hazard_score"]
        + 0.35 * df["exposure_score"]
        + 0.25 * df["sensitivity_score"]
    )

    # Illustrative alert bands, not official thresholds.
    df["priority_level"] = pd.cut(
        df["priority_score"],
        bins=[-0.001, 0.25, 0.50, 0.75, 1.0],
        labels=["Low", "Moderate", "High", "Very High"]
    )

    return df.sort_values(
        "priority_score",
        ascending=False
    ).reset_index(drop=True)
