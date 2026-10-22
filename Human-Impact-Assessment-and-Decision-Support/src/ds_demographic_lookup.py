
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parents[1]

FEATURES = [
    "total_population",
    "children_0_14_ratio",
    "elderly_60_plus_ratio",
    "female_ratio",
    "unprotected_well_ratio",
    "no_toilet_ratio",
    "public_toilet_ratio",
]

SOURCES = {
    "flood": BASE_DIR / "data/final/flood_train.csv",
    "landslide": BASE_DIR / "data/final/landslide_train.csv",
}


def normalize_name(value):
    return " ".join(str(value).strip().lower().split())


def load_ds_demographics():
    records = []

    for hazard, path in SOURCES.items():
        df = pd.read_csv(path)

        required = ["District", "Division"] + FEATURES

        missing = [
            column for column in required
            if column not in df.columns
        ]

        if missing:
            raise ValueError(
                f"{hazard} dataset missing columns: {missing}"
            )

        df = df[required].copy()
        df["source_hazard"] = hazard

        records.append(df)

    combined = pd.concat(records, ignore_index=True)

    combined = combined.dropna(
        subset=["District", "Division"] + FEATURES
    )

    combined["district_key"] = combined[
        "District"
    ].map(normalize_name)

    combined["division_key"] = combined[
        "Division"
    ].map(normalize_name)

    for feature in FEATURES:
        combined[feature] = pd.to_numeric(
            combined[feature],
            errors="coerce"
        )

    combined = combined.dropna(subset=FEATURES)

    # Remove repeated identical demographic profiles.
    unique_profiles = combined.drop_duplicates(
        subset=["district_key", "division_key"] + FEATURES
    )

    profile_counts = (
        unique_profiles
        .groupby(["district_key", "division_key"])
        .size()
        .reset_index(name="profile_count")
    )

    # Only automatically select a profile when
    # exactly one unique profile exists for the DS.
    unambiguous = profile_counts[
        profile_counts["profile_count"] == 1
    ][["district_key", "division_key"]]

    lookup = unique_profiles.merge(
        unambiguous,
        on=["district_key", "division_key"],
        how="inner"
    )

    lookup = lookup.drop_duplicates(
        subset=["district_key", "division_key"]
    )

    return lookup.sort_values(
        ["District", "Division"]
    ).reset_index(drop=True), profile_counts


if __name__ == "__main__":
    lookup, profile_counts = load_ds_demographics()

    print("\nDS DEMOGRAPHIC LOOKUP")
    print("=====================")

    print("Unambiguous DS profiles:", len(lookup))
    print("DS divisions reviewed:", len(profile_counts))

    ambiguous = profile_counts[
        profile_counts["profile_count"] > 1
    ]

    print(
        "DS divisions with conflicting profiles:",
        len(ambiguous)
    )

    print("\nExample lookup records:")

    print(
        lookup[
            ["District", "Division"] + FEATURES
        ].head(5).to_string(index=False)
    )

    if not ambiguous.empty:
        print("\nConflicting DS profiles requiring review:")
        print(ambiguous.head(10).to_string(index=False))
