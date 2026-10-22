# %%

import pandas as pd
import numpy as np
import joblib
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix
)
from xgboost import XGBClassifier

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")
FINAL = BASE / "data/final"
MODELS = BASE / "models"
MODELS.mkdir(parents=True, exist_ok=True)

demographic_features = [
    "total_population",
    "children_0_14_ratio",
    "elderly_60_plus_ratio",
    "female_ratio",
    "unprotected_well_ratio",
    "no_toilet_ratio",
    "public_toilet_ratio"
]

landslide_features = demographic_features + [
    "pre_rfh_1dekad",
    "pre_r1h",
    "pre_r3h",
    "pre_rfq",
    "pre_r1q",
    "pre_r3q"
]

risk_names = ["Low", "Moderate", "High", "Very High"]
risk_to_number = {
    name: i for i, name in enumerate(risk_names)
}

results = []

for hazard in ["flood", "landslide"]:

    train = pd.read_csv(FINAL / f"{hazard}_train.csv")
    test = pd.read_csv(FINAL / f"{hazard}_test.csv")

    features = (
        demographic_features
        if hazard == "flood"
        else landslide_features
    )

    X_train = train[features].apply(
        pd.to_numeric, errors="coerce"
    )
    X_test = test[features].apply(
        pd.to_numeric, errors="coerce"
    )

    y_train = train["risk_level"].map(risk_to_number).astype(int)
    y_test = test["risk_level"].map(risk_to_number).astype(int)

    # Fill missing values using training data only
    medians = X_train.median()
    X_train = X_train.fillna(medians)
    X_test = X_test.fillna(medians)

    models = {
        "RandomForest": RandomForestClassifier(
            n_estimators=200,
            max_depth=6,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1
        ),
        "XGBoost": XGBClassifier(
            n_estimators=150,
            max_depth=3,
            learning_rate=0.05,
            subsample=0.8,
            colsample_bytree=0.8,
            objective="multi:softprob",
            num_class=4,
            random_state=42,
            n_jobs=2
        )
    }

    for model_name, model in models.items():

        model.fit(X_train, y_train)
        predictions = model.predict(X_test)

        accuracy = accuracy_score(y_test, predictions)
        balanced_acc = balanced_accuracy_score(
            y_test, predictions
        )
        macro_f1 = f1_score(
            y_test, predictions,
            average="macro",
            zero_division=0
        )

        results.append({
            "Hazard": hazard,
            "Model": model_name,
            "Accuracy": round(accuracy, 4),
            "Balanced_Accuracy": round(balanced_acc, 4),
            "Macro_F1": round(macro_f1, 4)
        })

        joblib.dump(
            {
                "model": model,
                "features": features,
                "medians": medians,
                "risk_names": risk_names
            },
            MODELS / f"{hazard}_{model_name}_real.joblib"
        )

        print("\n" + "=" * 60)
        print(hazard.upper(), "-", model_name)
        print("=" * 60)

        print("Accuracy:", round(accuracy, 4))
        print("Balanced accuracy:", round(balanced_acc, 4))
        print("Macro F1:", round(macro_f1, 4))

        print("\nClassification report:")
        print(classification_report(
            y_test,
            predictions,
            labels=[0, 1, 2, 3],
            target_names=risk_names,
            zero_division=0
        ))

        print("Confusion matrix:")
        print(confusion_matrix(
            y_test,
            predictions,
            labels=[0, 1, 2, 3]
        ))

results_df = pd.DataFrame(results)

results_df.to_csv(
    FINAL / "real_model_baseline_results.csv",
    index=False
)

print("\n" + "=" * 60)
print("FINAL MODEL COMPARISON")
print("=" * 60)
print(results_df.to_string(index=False))

print("\nModel training completed!")
print("Models saved in:", MODELS)


import pandas as pd
import numpy as np
from pathlib import Path

from imblearn.over_sampling import RandomOverSampler
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    classification_report
)

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")
FINAL = BASE / "data/final"

train = pd.read_csv(FINAL / "landslide_train.csv")
test = pd.read_csv(FINAL / "landslide_test.csv")

features = [
    "total_population",
    "children_0_14_ratio",
    "elderly_60_plus_ratio",
    "female_ratio",
    "unprotected_well_ratio",
    "no_toilet_ratio",
    "public_toilet_ratio",
    "pre_rfh_1dekad",
    "pre_r1h",
    "pre_r3h",
    "pre_rfq",
    "pre_r1q",
    "pre_r3q"
]

risk_names = ["Low", "Moderate", "High", "Very High"]
risk_map = {name: i for i, name in enumerate(risk_names)}

X_train = train[features].apply(pd.to_numeric, errors="coerce")
X_test = test[features].apply(pd.to_numeric, errors="coerce")

y_train = train["risk_level"].map(risk_map).astype(int)
y_test = test["risk_level"].map(risk_map).astype(int)

medians = X_train.median()
X_train = X_train.fillna(medians)
X_test = X_test.fillna(medians)

# Baseline model
baseline = RandomForestClassifier(
    n_estimators=200,
    max_depth=6,
    min_samples_leaf=3,
    random_state=42,
    n_jobs=-1
)

baseline.fit(X_train, y_train)
baseline_pred = baseline.predict(X_test)

# Training-only oversampling
sampler = RandomOverSampler(random_state=42)

X_aug, y_aug = sampler.fit_resample(X_train, y_train)

augmented = RandomForestClassifier(
    n_estimators=200,
    max_depth=6,
    min_samples_leaf=3,
    random_state=42,
    n_jobs=-1
)

augmented.fit(X_aug, y_aug)
augmented_pred = augmented.predict(X_test)

comparison = pd.DataFrame([
    {
        "Training": "Real only",
        "Training_records": len(X_train),
        "Accuracy": accuracy_score(y_test, baseline_pred),
        "Balanced_Accuracy": balanced_accuracy_score(
            y_test, baseline_pred
        ),
        "Macro_F1": f1_score(
            y_test, baseline_pred,
            average="macro",
            zero_division=0
        )
    },
    {
        "Training": "Real + oversampling",
        "Training_records": len(X_aug),
        "Accuracy": accuracy_score(y_test, augmented_pred),
        "Balanced_Accuracy": balanced_accuracy_score(
            y_test, augmented_pred
        ),
        "Macro_F1": f1_score(
            y_test, augmented_pred,
            average="macro",
            zero_division=0
        )
    }
])

print("=" * 65)
print("LANDSLIDE AUGMENTATION EXPERIMENT")
print("=" * 65)

print("\nOriginal training records:", len(X_train))
print("Oversampled training records:", len(X_aug))
print("Untouched real testing records:", len(X_test))

print("\nClass counts before oversampling:")
print(y_train.value_counts().sort_index())

print("\nClass counts after oversampling:")
print(y_aug.value_counts().sort_index())

print("\nMODEL COMPARISON:")
print(comparison.to_string(index=False))

print("\nAugmented model classification report:")
print(classification_report(
    y_test,
    augmented_pred,
    labels=[0, 1, 2, 3],
    target_names=risk_names,
    zero_division=0
))

comparison.to_csv(
    FINAL / "landslide_oversampling_comparison.csv",
    index=False
)

print("\nSaved comparison results.")


# %%
import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

kalu = pd.read_csv(
    BASE / "data/final/flood_kalu_hydrology_training_candidates.csv"
)

print("Dataset shape:", kalu.shape)

print("\nALL COLUMNS:")
for column in kalu.columns:
    print(column)

print("\nFIRST 3 RECORDS:")
display(kalu.head(3))

print("\nMISSING VALUES:")
print(kalu.isna().sum().to_string())

# %%

import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import GroupShuffleSplit
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    classification_report
)

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")
FINAL = BASE / "data/final"

df = pd.read_csv(
    FINAL / "flood_kalu_hydrology_training_candidates.csv"
)

demographic_features = [
    "total_population",
    "children_0_14_ratio",
    "elderly_60_plus_ratio",
    "female_ratio",
    "unprotected_well_ratio",
    "no_toilet_ratio",
    "public_toilet_ratio"
]

hydrology_features = [
    "pre_wl_1d",
    "pre_wl_max_3d",
    "pre_wl_avg_7d",
    "pre_q_1d",
    "pre_q_max_3d",
    "pre_q_avg_7d"
]

# Check all required columns exist
required = (
    demographic_features
    + hydrology_features
    + ["affected_target", "episode_id"]
)

missing = [c for c in required if c not in df.columns]

if missing:
    raise ValueError(f"Missing columns: {missing}")

# Keep only usable target records
df["affected_target"] = pd.to_numeric(
    df["affected_target"], errors="coerce"
)

df = df[
    df["affected_target"].notna()
    & (df["affected_target"] >= 0)
    & df["episode_id"].notna()
].copy()

# Split by provisional disaster episode
splitter = GroupShuffleSplit(
    n_splits=1,
    test_size=0.20,
    random_state=42
)

train_idx, test_idx = next(
    splitter.split(df, groups=df["episode_id"])
)

train = df.iloc[train_idx].copy()
test = df.iloc[test_idx].copy()

# Define four risk categories using training targets only
thresholds = train["affected_target"].quantile(
    [0.25, 0.50, 0.75]
).to_numpy()

if len(np.unique(thresholds)) < 3:
    raise ValueError(
        "Quantile thresholds overlap; review the target distribution."
    )

def assign_risk(values):
    return np.searchsorted(
        thresholds,
        np.asarray(values),
        side="right"
    )

train["risk_code"] = assign_risk(train["affected_target"])
test["risk_code"] = assign_risk(test["affected_target"])

risk_names = ["Low", "Moderate", "High", "Very High"]

print("Training records:", len(train))
print("Testing records:", len(test))
print("Training episodes:", train["episode_id"].nunique())
print("Testing episodes:", test["episode_id"].nunique())
print("Risk thresholds:", thresholds)

results = []

experiments = {
    "Demographics only": demographic_features,
    "Demographics + hydrology": (
        demographic_features + hydrology_features
    )
}

for experiment_name, features in experiments.items():

    X_train = train[features].apply(
        pd.to_numeric, errors="coerce"
    )
    X_test = test[features].apply(
        pd.to_numeric, errors="coerce"
    )

    medians = X_train.median()
    X_train = X_train.fillna(medians)
    X_test = X_test.fillna(medians)

    y_train = train["risk_code"]
    y_test = test["risk_code"]

    model = RandomForestClassifier(
        n_estimators=200,
        max_depth=6,
        min_samples_leaf=3,
        random_state=42,
        n_jobs=-1
    )

    model.fit(X_train, y_train)
    predictions = model.predict(X_test)

    results.append({
        "Experiment": experiment_name,
        "Train_records": len(train),
        "Test_records": len(test),
        "Accuracy": round(
            accuracy_score(y_test, predictions), 4
        ),
        "Balanced_Accuracy": round(
            balanced_accuracy_score(y_test, predictions), 4
        ),
        "Macro_F1": round(
            f1_score(
                y_test,
                predictions,
                labels=[0, 1, 2, 3],
                average="macro",
                zero_division=0
            ), 4
        )
    })

    print("\n" + "=" * 60)
    print(experiment_name)
    print("=" * 60)

    print(classification_report(
        y_test,
        predictions,
        labels=[0, 1, 2, 3],
        target_names=risk_names,
        zero_division=0
    ))

comparison = pd.DataFrame(results)

print("\n" + "=" * 70)
print("FINAL KALU HYDROLOGY COMPARISON")
print("=" * 70)
print(comparison.to_string(index=False))

comparison.to_csv(
    FINAL / "kalu_hydrology_model_comparison.csv",
    index=False
)

print("\nResults saved successfully.")


# %%

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


# %%
from pathlib import Path

file = Path(
    "/Users/ohaseelanka/disaster_analytics_hub/outputs/flood_ds_priority_demo.csv"
)

print("File exists:", file.exists())
print("File location:", file)

# %%
import sys
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

sys.path.insert(0, str(BASE / "src"))

from human_impact_scoring import calculate_human_impact_priority

df = pd.read_csv(
    BASE / "data/final/flood_demographic_training_candidates.csv"
)

df = df.drop_duplicates(
    subset=["District", "Division"]
).copy()

rng = np.random.default_rng(42)
df["hazard_severity"] = rng.uniform(0.2, 0.95, len(df))

result = calculate_human_impact_priority(df)

output_folder = BASE / "outputs"
output_folder.mkdir(parents=True, exist_ok=True)

output_file = output_folder / "flood_ds_priority_demo.csv"
result.to_csv(output_file, index=False)

print("SUCCESS!")
print("File created:", output_file.exists())
print("Total DS divisions:", len(result))

print("\nPriority distribution:")
print(result["priority_level"].value_counts())

display(result[[
    "District",
    "Division",
    "priority_score",
    "priority_level"
]].head(10))

# %%

import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

df = pd.read_csv(
    BASE / "outputs/flood_ds_priority_demo.csv"
)

# Explain the existing weighted priority score
df["hazard_contribution"] = 0.40 * df["hazard_score"]
df["exposure_contribution"] = 0.35 * df["exposure_score"]
df["sensitivity_contribution"] = 0.25 * df["sensitivity_score"]

# Identify the largest contribution to each score
contribution_columns = {
    "hazard_contribution": "Hazard severity",
    "exposure_contribution": "Population exposure",
    "sensitivity_contribution": "Social sensitivity"
}

df["main_risk_driver"] = (
    df[
        list(contribution_columns.keys())
    ]
    .idxmax(axis=1)
    .map(contribution_columns)
)

# Verify contributions reproduce the original score
reconstructed = (
    df["hazard_contribution"]
    + df["exposure_contribution"]
    + df["sensitivity_contribution"]
)

assert (
    (reconstructed - df["priority_score"]).abs().max()
    < 1e-8
), "Score calculation mismatch!"

columns = [
    "District",
    "Division",
    "priority_score",
    "priority_level",
    "hazard_contribution",
    "exposure_contribution",
    "sensitivity_contribution",
    "main_risk_driver"
]

output_file = (
    BASE / "outputs/flood_ds_explainable_priority_demo.csv"
)

df.to_csv(output_file, index=False)

print("STEP 17 — EXPLAINABLE PRIORITY RESULTS")
print("DS divisions:", len(df))
print("Output saved:", output_file.exists())

print("\nMain risk drivers:")
print(df["main_risk_driver"].value_counts())

print("\nTop 10 DS divisions with explanations:")
display(df[columns].head(10))


# %%

import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

df = pd.read_csv(
    BASE / "outputs/flood_ds_explainable_priority_demo.csv"
)

# Keep only the columns needed by the dashboard
dashboard = df[
    [
        "District",
        "Division",
        "hazard_severity",
        "hazard_score",
        "exposure_score",
        "sensitivity_score",
        "priority_score",
        "priority_level",
        "hazard_contribution",
        "exposure_contribution",
        "sensitivity_contribution",
        "main_risk_driver"
    ]
].copy()

# Add explicit metadata to prevent simulated results
# from being mistaken for operational disaster warnings.
dashboard["hazard_type"] = "Flood"
dashboard["scenario_type"] = "Simulated demonstration"
dashboard["score_method"] = "Provisional weighted H-E-S"
dashboard["operational_warning"] = False

dashboard = dashboard.sort_values(
    "priority_score",
    ascending=False
).reset_index(drop=True)

dashboard["priority_rank"] = range(1, len(dashboard) + 1)

output = BASE / "outputs/tables"
output.mkdir(parents=True, exist_ok=True)

csv_path = output / "flood_dashboard_demo.csv"
json_path = output / "flood_dashboard_demo.json"

dashboard.to_csv(csv_path, index=False)
dashboard.to_json(
    json_path,
    orient="records",
    indent=2
)

print("STEP 18 — DASHBOARD DATA")
print("DS divisions:", len(dashboard))
print("CSV saved:", csv_path.exists())
print("JSON saved:", json_path.exists())

print("\nPriority distribution:")
print(dashboard["priority_level"].value_counts())

print("\nTop 5 dashboard records:")
display(dashboard.head(5))


# %%
import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

files = [
    BASE / "data/processed/census_ds_features.parquet",
    BASE / "data/processed/flood_ds_features.parquet"
]

for file in files:
    df = pd.read_parquet(file)

    print("\nFILE:", file.name)
    print("Rows:", len(df))
    print("Columns:", df.columns.tolist())

    geometry_columns = [
        c for c in df.columns
        if any(word in c.lower() for word in [
            "geometry", "geom", "wkt", "latitude",
            "longitude", "centroid"
        ])
    ]

    print("Possible geometry columns:", geometry_columns)

# %%
import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

df = pd.read_csv(
    BASE / "data/final/flood_demographic_training_candidates.csv",
    nrows=3
)

print("GIS-related columns:")
for col in df.columns:
    if any(x in col.lower() for x in [
        "geometry", "geom", "wkt",
        "latitude", "longitude",
        "centroid", "adm3", "ds_code"
    ]):
        print(col)

# %%
import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

df = pd.read_csv(
    BASE / "outputs/tables/flood_dashboard_demo.csv"
)

source = pd.read_csv(
    BASE / "data/final/flood_demographic_training_candidates.csv"
)

codes = source[
    ["District", "Division", "ds_code", "adm3_pcode"]
].drop_duplicates(
    subset=["District", "Division"]
)

merged = df.merge(
    codes,
    on=["District", "Division"],
    how="left"
)

print("Total DS divisions:", len(merged))
print("DS divisions with ADM3 codes:", merged["adm3_pcode"].notna().sum())
print("DS divisions missing ADM3 codes:", merged["adm3_pcode"].isna().sum())

print("\nDivisions missing geographic codes:")
display(
    merged.loc[
        merged["adm3_pcode"].isna(),
        ["District", "Division"]
    ]
)

# %%
from pathlib import Path
import pandas as pd

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

source = pd.read_csv(
    BASE / "data/final/flood_demographic_training_candidates.csv"
)

dashboard = pd.read_csv(
    BASE / "outputs/tables/flood_dashboard_demo.csv"
)

codes = source[
    ["District", "Division", "ds_code", "adm3_pcode"]
].drop_duplicates(
    subset=["District", "Division"]
)

report = dashboard[
    ["District", "Division", "priority_score", "priority_level"]
].merge(
    codes,
    on=["District", "Division"],
    how="left",
    validate="one_to_one"
)

report["mapping_status"] = report["adm3_pcode"].apply(
    lambda value: "Code available"
    if pd.notna(value)
    else "Needs boundary matching"
)

output = BASE / "outputs/gis"
output.mkdir(parents=True, exist_ok=True)

report.to_csv(
    output / "flood_ds_boundary_matching_report.csv",
    index=False
)

print("Total divisions:", len(report))
print("\nMapping status:")
print(report["mapping_status"].value_counts())
print("\nSaved matching report successfully.")

# %%
import json
import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

# Load the dashboard data
dashboard = pd.read_csv(
    BASE / "outputs/tables/flood_dashboard_demo.csv"
)

# Load the Sri Lanka ADM3 boundary file
with open(
    BASE / "gis/boundaries/sri_lanka_adm3.geojson",
    encoding="utf-8"
) as f:
    geojson = json.load(f)

# Extract boundary names and IDs
boundaries = pd.DataFrame([
    {
        "boundary_name": feature["properties"].get("shapeName"),
        "shapeID": feature["properties"].get("shapeID")
    }
    for feature in geojson["features"]
])

# Normalize names for initial comparison
def normalize_name(name):
    return "".join(
        char for char in str(name).lower()
        if char.isalnum()
    )

dashboard["name_key"] = dashboard["Division"].apply(normalize_name)
boundaries["name_key"] = boundaries["boundary_name"].apply(normalize_name)

# Only accept unique exact normalized-name matches
name_counts = boundaries["name_key"].value_counts()
unique_boundaries = boundaries[
    boundaries["name_key"].map(name_counts) == 1
]

matched = dashboard.merge(
    unique_boundaries,
    on="name_key",
    how="left",
    validate="many_to_one"
)

print("Total dashboard divisions:", len(matched))
print("Boundary polygons:", len(boundaries))
print("Exact name matches:", matched["shapeID"].notna().sum())
print("Unmatched divisions:", matched["shapeID"].isna().sum())

print("\nUnmatched DS divisions:")
display(
    matched.loc[
        matched["shapeID"].isna(),
        ["District", "Division"]
    ]
)

# %%
from difflib import get_close_matches

unmatched = matched[
    matched["shapeID"].isna()
][["District", "Division"]]

boundary_names = sorted(
    boundaries["boundary_name"].dropna().unique()
)

for _, row in unmatched.iterrows():
    division = row["Division"]
    district = row["District"]

    suggestions = get_close_matches(
        division,
        boundary_names,
        n=5,
        cutoff=0.45
    )

    print(f"\n{district} — {division}")
    print("Possible boundary names:", suggestions)

# %%
# Search for Hanwella and Seethawaka in the boundary dataset
search_terms = [
    "hanwella",
    "seethawaka",
    "seethawaka",
    "sitawaka",
    "seethawaka",
]

print("Relevant boundary names:")

for name in sorted(boundaries["boundary_name"].dropna().unique()):
    if any(term in name.lower() for term in search_terms):
        print(name)

# Check whether proposed matches are unique in the boundary dataset
candidate_names = [
    "Matugama",
    "Kahawattha",
    "Yatiyantota",
    "Aranayake",
    "Walallawita",
    "Dehiowita",
    "Bulathkohipitiya",
    "Opanayake",
]

print("\nCandidate boundary name counts:")

for name in candidate_names:
    count = (
        boundaries["boundary_name"]
        .str.casefold()
        .eq(name.casefold())
        .sum()
    )
    print(f"{name}: {count}")

# %%
import json
import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

dashboard = pd.read_csv(
    BASE / "outputs/tables/flood_dashboard_demo.csv"
)

with open(
    BASE / "gis/boundaries/sri_lanka_adm3.geojson",
    encoding="utf-8"
) as f:
    geojson = json.load(f)

boundaries = pd.DataFrame([
    {
        "boundary_name": feature["properties"]["shapeName"],
        "shapeID": feature["properties"]["shapeID"]
    }
    for feature in geojson["features"]
])

def normalize_name(name):
    return "".join(
        c for c in str(name).lower()
        if c.isalnum()
    )

# Candidate spelling corrections
name_corrections = {
    "Mathugama": "Matugama",
    "Kahawatta": "Kahawattha",
    "Yatiyanthota": "Yatiyantota",
    "Aranayaka": "Aranayake",
    "Walallavita": "Walallawita",
    "Dehiovita": "Dehiowita",
    "Bulathkohupitiya": "Bulathkohipitiya",
    "Opanayaka": "Opanayake"
}

dashboard["boundary_lookup_name"] = (
    dashboard["Division"]
    .replace(name_corrections)
)

dashboard["name_key"] = (
    dashboard["boundary_lookup_name"]
    .apply(normalize_name)
)

boundaries["name_key"] = (
    boundaries["boundary_name"]
    .apply(normalize_name)
)

# Avoid ambiguous boundary-name matches
counts = boundaries["name_key"].value_counts()

unique_boundaries = boundaries[
    boundaries["name_key"].map(counts) == 1
]

mapping = dashboard.merge(
    unique_boundaries,
    on="name_key",
    how="left",
    validate="many_to_one"
)

mapping["match_status"] = mapping.apply(
    lambda row:
        "Unresolved"
        if pd.isna(row["shapeID"])
        else (
            "Spelling candidate"
            if row["Division"] in name_corrections
            else "Exact name candidate"
        ),
    axis=1
)

output_dir = BASE / "outputs/gis"
output_dir.mkdir(parents=True, exist_ok=True)

mapping.to_csv(
    output_dir / "flood_ds_provisional_boundary_mapping.csv",
    index=False
)

print("Total DS divisions:", len(mapping))
print("Matched candidates:", mapping["shapeID"].notna().sum())
print("Unresolved:", mapping["shapeID"].isna().sum())

print("\nMatch status:")
print(mapping["match_status"].value_counts())

print("\nUnresolved divisions:")
display(
    mapping.loc[
        mapping["shapeID"].isna(),
        ["District", "Division"]
    ]
)

# %%
import json
import pandas as pd
from pathlib import Path
from shapely.geometry import shape

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

# Load provisional matching file
mapping = pd.read_csv(
    BASE / "outputs/gis/flood_ds_provisional_boundary_mapping.csv"
)

# Load ADM2 and ADM3 GeoJSON
with open(BASE / "gis/boundaries/sri_lanka_adm2.geojson") as f:
    adm2 = json.load(f)

with open(BASE / "gis/boundaries/sri_lanka_adm3.geojson") as f:
    adm3 = json.load(f)

# Build district polygon lookup
district_polygons = {
    feature["properties"]["shapeName"].replace(" District", ""):
    shape(feature["geometry"])
    for feature in adm2["features"]
}

# Build DS polygon lookup
ds_polygons = {
    feature["properties"]["shapeID"]:
    shape(feature["geometry"])
    for feature in adm3["features"]
}

results = []

for _, row in mapping.iterrows():

    district = row["District"]
    division = row["Division"]
    shape_id = row["shapeID"]

    if pd.isna(shape_id):
        status = "Unresolved"
        overlap_ratio = None

    elif district not in district_polygons:
        status = "District not found"
        overlap_ratio = None

    else:
        ds_polygon = ds_polygons.get(shape_id)
        district_polygon = district_polygons[district]

        if ds_polygon is None:
            status = "DS polygon not found"
            overlap_ratio = None
        else:
            # Calculate overlap in the same coordinate system.
            # Ratio is used for checking membership, not area reporting.
            overlap_ratio = (
                ds_polygon.intersection(district_polygon).area
                / ds_polygon.area
            )

            if overlap_ratio >= 0.95:
                status = "District verified"
            else:
                status = "Needs review"

    results.append({
        "District": district,
        "Division": division,
        "shapeID": shape_id,
        "district_overlap_ratio": overlap_ratio,
        "verification_status": status
    })

verification = pd.DataFrame(results)

output_path = (
    BASE / "outputs/gis/flood_ds_district_verification.csv"
)

verification.to_csv(output_path, index=False)

print("Total divisions:", len(verification))

print("\nVerification results:")
print(verification["verification_status"].value_counts())

print("\nDivisions needing review:")
display(
    verification[
        verification["verification_status"] != "District verified"
    ]
)

# %%
import pandas as pd
from shapely.validation import explain_validity
from shapely.ops import unary_union

review = verification[
    verification["verification_status"] == "Needs review"
].copy()

results = []

for _, row in review.iterrows():
    ds = ds_polygons[row["shapeID"]]
    district = district_polygons[row["District"]]

    # Repair invalid geometries if necessary
    ds_fixed = ds if ds.is_valid else ds.buffer(0)
    district_fixed = (
        district if district.is_valid else district.buffer(0)
    )

    # Representative point is guaranteed to lie inside its polygon
    point = ds_fixed.representative_point()

    results.append({
        "District": row["District"],
        "Division": row["Division"],
        "Original overlap": row["district_overlap_ratio"],
        "DS geometry valid": ds.is_valid,
        "District geometry valid": district.is_valid,
        "Geometry issue": (
            "None" if ds.is_valid else explain_validity(ds)
        ),
        "Representative point inside district":
            district_fixed.covers(point),
        "Repaired overlap": (
            ds_fixed.intersection(district_fixed).area
            / ds_fixed.area
            if ds_fixed.area > 0 else None
        )
    })

review_results = pd.DataFrame(results)

display(review_results)

review_results.to_csv(
    BASE / "outputs/gis/flood_ds_boundary_review.csv",
    index=False
)

print("\nRepresentative point results:")
print(
    review_results[
        "Representative point inside district"
    ].value_counts()
)

# %%
from shapely.geometry import shape

# Find Seethawaka in the ADM3 dataset
seethawaka_features = [
    feature
    for feature in adm3["features"]
    if feature["properties"]["shapeName"].lower() == "seethawaka"
]

print("Seethawaka polygons found:", len(seethawaka_features))

for feature in seethawaka_features:
    polygon = shape(feature["geometry"])
    district = district_polygons["Colombo"]

    if not polygon.is_valid:
        polygon = polygon.buffer(0)

    if not district.is_valid:
        district = district.buffer(0)

    print("\nBoundary name:", feature["properties"]["shapeName"])
    print("Shape ID:", feature["properties"]["shapeID"])
    print(
        "Representative point inside Colombo:",
        district.covers(polygon.representative_point())
    )
    print(
        "Overlap with Colombo:",
        round(
            polygon.intersection(district).area / polygon.area,
            4
        )
    )

# %%
import json
import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

mapping = pd.read_csv(
    BASE / "outputs/gis/flood_ds_provisional_boundary_mapping.csv"
)

verification = pd.read_csv(
    BASE / "outputs/gis/flood_ds_district_verification.csv"
)

with open(
    BASE / "gis/boundaries/sri_lanka_adm3.geojson",
    encoding="utf-8"
) as f:
    adm3 = json.load(f)

# Attach geographic verification status
mapping = mapping.merge(
    verification[
        ["District", "Division", "verification_status",
         "district_overlap_ratio"]
    ],
    on=["District", "Division"],
    how="left",
    validate="one_to_one"
)

# Lookup polygons by shapeID
polygon_lookup = {
    feature["properties"]["shapeID"]: feature
    for feature in adm3["features"]
}

features = []

for _, row in mapping.iterrows():

    if pd.isna(row["shapeID"]):
        continue

    shape_id = row["shapeID"]
    boundary = polygon_lookup.get(shape_id)

    if boundary is None:
        continue

    properties = {
        "District": row["District"],
        "Division": row["Division"],
        "boundary_name": row["boundary_name"],
        "shapeID": shape_id,
        "priority_score": float(row["priority_score"]),
        "priority_level": row["priority_level"],
        "match_status": row["match_status"],
        "verification_status": row["verification_status"],
        "district_overlap_ratio": (
            float(row["district_overlap_ratio"])
            if pd.notna(row["district_overlap_ratio"])
            else None
        ),
        "scenario_type": "Simulated demonstration",
        "operational_warning": False
    }

    features.append({
        "type": "Feature",
        "properties": properties,
        "geometry": boundary["geometry"]
    })

map_geojson = {
    "type": "FeatureCollection",
    "features": features
}

output = BASE / "outputs/gis/flood_ds_priority_map.geojson"

with open(output, "w", encoding="utf-8") as f:
    json.dump(map_geojson, f)

print("Map polygons created:", len(features))
print("Saved:", output)

print("\nGeographic verification status:")
print(
    pd.Series([
        f["properties"]["verification_status"]
        for f in features
    ]).value_counts()
)

print("\nUnmapped divisions:")
print(
    mapping.loc[
        mapping["shapeID"].isna(),
        ["District", "Division"]
    ].to_string(index=False)
)

# %%
import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

results = pd.read_csv(
    BASE / "data/final/real_model_baseline_results.csv"
)

print("Columns:")
print(results.columns.tolist())

print("\nExisting model results:")
print(results.to_string(index=False))

# %%
import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

for hazard in ["flood", "landslide"]:

    print("\n" + "=" * 65)
    print(hazard.upper(), "DATASET DIAGNOSIS")
    print("=" * 65)

    train = pd.read_csv(
        BASE / f"data/final/{hazard}_train.csv"
    )

    test = pd.read_csv(
        BASE / f"data/final/{hazard}_test.csv"
    )

    print("\nTraining rows:", len(train))
    print("Testing rows:", len(test))

    print("\nAvailable columns:")
    print(train.columns.tolist())

    print("\nMissing values:")
    print(
        train.isna().sum()[
            train.isna().sum() > 0
        ].sort_values(ascending=False).head(15)
    )

    print("\nPossible target columns:")
    target_columns = [
        col for col in train.columns
        if any(word in col.lower() for word in
               ["target", "label", "class", "severity", "impact"])
    ]

    for col in target_columns:
        print(f"\n{col}")
        print("Training:")
        print(train[col].value_counts(dropna=False).head(10))
        print("Testing:")
        if col in test.columns:
            print(test[col].value_counts(dropna=False).head(10))

    print("\nDuplicate training rows:", train.duplicated().sum())
    print("\nDuplicate testing rows:", test.duplicated().sum())

# %%
import pandas as pd
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

for hazard in ["flood", "landslide"]:

    train = pd.read_csv(
        BASE / f"data/final/{hazard}_train.csv"
    )

    test = pd.read_csv(
        BASE / f"data/final/{hazard}_test.csv"
    )

    print(f"\n{'=' * 55}")
    print(f"{hazard.upper()} — CLASS DISTRIBUTION")
    print(f"{'=' * 55}")

    comparison = pd.DataFrame({
        "Train": train["risk_level"].value_counts(),
        "Test": test["risk_level"].value_counts()
    }).fillna(0).astype(int)

    comparison["Train %"] = (
        comparison["Train"] / len(train) * 100
    ).round(1)

    comparison["Test %"] = (
        comparison["Test"] / len(test) * 100
    ).round(1)

    print(comparison.to_string())

    majority_accuracy = (
        test["risk_level"].value_counts().max()
        / len(test) * 100
    )

    print(
        f"\nTest majority-class baseline: "
        f"{majority_accuracy:.2f}%"
    )

    print(
        "Unique training episodes:",
        train["episode_id"].nunique()
    )

    print(
        "Unique testing episodes:",
        test["episode_id"].nunique()
    )

    shared_episodes = (
        set(train["episode_id"])
        & set(test["episode_id"])
    )

    print(
        "Episodes shared between train and test:",
        len(shared_episodes)
    )

# %%
import pandas as pd
import numpy as np

from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_validate

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

train = pd.read_csv(
    BASE / "data/final/flood_train.csv"
)

feature_sets = {
    "Demographics": [
        "total_population",
        "children_0_14_ratio",
        "elderly_60_plus_ratio",
        "female_ratio",
        "unprotected_well_ratio",
        "no_toilet_ratio",
        "public_toilet_ratio"
    ],

    "Demographics + location": [
        "total_population",
        "children_0_14_ratio",
        "elderly_60_plus_ratio",
        "female_ratio",
        "unprotected_well_ratio",
        "no_toilet_ratio",
        "public_toilet_ratio",
        "center_lat",
        "center_lon"
    ],

    "Demographics + infrastructure": [
        "total_population",
        "children_0_14_ratio",
        "elderly_60_plus_ratio",
        "female_ratio",
        "unprotected_well_ratio",
        "no_toilet_ratio",
        "public_toilet_ratio",
        "area_sqkm",
        "road_density",
        "facility_density"
    ]
}

results = []

for name, features in feature_sets.items():

    X = train[features].copy()

    # Missing-value indicators can preserve useful
    # information about data availability.
    for col in features:
        if X[col].isna().any():
            X[col + "_missing"] = X[col].isna().astype(int)

    # Median imputation must be fitted separately
    # inside each cross-validation fold.
    from sklearn.pipeline import Pipeline
    from sklearn.impute import SimpleImputer

    model = Pipeline([
        ("imputer", SimpleImputer(
            strategy="median",
            keep_empty_features=True
        )),
        ("classifier", RandomForestClassifier(
            n_estimators=300,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1
        ))
    ])

    cv = GroupKFold(n_splits=5)

    scores = cross_validate(
        model,
        X,
        train["risk_level"],
        groups=train["episode_id"],
        cv=cv,
        scoring={
            "accuracy": "accuracy",
            "balanced_accuracy": "balanced_accuracy",
            "macro_f1": "f1_macro"
        },
        n_jobs=1
    )

    results.append({
        "Feature Set": name,
        "CV Accuracy": scores["test_accuracy"].mean(),
        "CV Balanced Accuracy":
            scores["test_balanced_accuracy"].mean(),
        "CV Macro F1": scores["test_macro_f1"].mean()
    })

comparison = pd.DataFrame(results)

print(
    comparison.sort_values(
        "CV Macro F1",
        ascending=False
    ).round(4).to_string(index=False)
)

# %%
import pandas as pd

from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

train = pd.read_csv(
    BASE / "data/final/flood_train.csv"
)

features = [
    "total_population",
    "children_0_14_ratio",
    "elderly_60_plus_ratio",
    "female_ratio",
    "unprotected_well_ratio",
    "no_toilet_ratio",
    "public_toilet_ratio"
]

X = train[features]
y = train["risk_level"]
groups = train["episode_id"]

configurations = [
    {"n_estimators": 300, "max_depth": None, "min_samples_leaf": 1},
    {"n_estimators": 300, "max_depth": None, "min_samples_leaf": 3},
    {"n_estimators": 300, "max_depth": 10, "min_samples_leaf": 2},
    {"n_estimators": 300, "max_depth": 6, "min_samples_leaf": 3},
    {"n_estimators": 300, "max_depth": 4, "min_samples_leaf": 5},
    {"n_estimators": 300, "max_depth": 8, "min_samples_leaf": 5},
]

results = []

cv = GroupKFold(n_splits=5)

for config in configurations:

    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("classifier", RandomForestClassifier(
            **config,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1
        ))
    ])

    scores = cross_validate(
        model,
        X,
        y,
        groups=groups,
        cv=cv,
        scoring={
            "accuracy": "accuracy",
            "balanced_accuracy": "balanced_accuracy",
            "macro_f1": "f1_macro"
        },
        n_jobs=1
    )

    results.append({
        **config,
        "CV Accuracy": scores["test_accuracy"].mean(),
        "CV Balanced Accuracy":
            scores["test_balanced_accuracy"].mean(),
        "CV Macro F1": scores["test_macro_f1"].mean()
    })

comparison = pd.DataFrame(results)

comparison = comparison.sort_values(
    "CV Macro F1",
    ascending=False
)

print(comparison.round(4).to_string(index=False))

comparison.to_csv(
    BASE / "data/final/flood_rf_tuning_results.csv",
    index=False
)

# %%
import pandas as pd
import joblib

from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix
)

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

train = pd.read_csv(BASE / "data/final/flood_train.csv")
test = pd.read_csv(BASE / "data/final/flood_test.csv")

features = [
    "total_population",
    "children_0_14_ratio",
    "elderly_60_plus_ratio",
    "female_ratio",
    "unprotected_well_ratio",
    "no_toilet_ratio",
    "public_toilet_ratio"
]

X_train = train[features]
y_train = train["risk_level"]

X_test = test[features]
y_test = test["risk_level"]

# Ensure provisional disaster episodes do not overlap.
assert not (
    set(train["episode_id"])
    & set(test["episode_id"])
), "Train/test episode overlap detected!"

model = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("classifier", RandomForestClassifier(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=5,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    ))
])

model.fit(X_train, y_train)

predictions = model.predict(X_test)

accuracy = accuracy_score(y_test, predictions)
balanced_accuracy = balanced_accuracy_score(
    y_test, predictions
)
macro_f1 = f1_score(
    y_test, predictions, average="macro"
)

print("FLOOD — HELD-OUT TEST RESULTS")
print("=" * 45)
print(f"Accuracy:          {accuracy:.4f}")
print(f"Balanced accuracy: {balanced_accuracy:.4f}")
print(f"Macro F1:          {macro_f1:.4f}")

print("\nClassification report:")
print(
    classification_report(
        y_test, predictions, zero_division=0
    )
)

labels = ["Low", "Moderate", "High", "Very High"]

print("\nConfusion matrix:")
print(
    pd.DataFrame(
        confusion_matrix(
            y_test, predictions, labels=labels
        ),
        index=[f"Actual {x}" for x in labels],
        columns=[f"Predicted {x}" for x in labels]
    )
)

# Save the fitted model and feature order.
model_path = BASE / "models/flood_rf_tuned.joblib"
model_path.parent.mkdir(parents=True, exist_ok=True)

joblib.dump(
    {
        "model": model,
        "features": features,
        "target": "risk_level",
        "evaluation": {
            "accuracy": accuracy,
            "balanced_accuracy": balanced_accuracy,
            "macro_f1": macro_f1
        }
    },
    model_path
)

print("\nSaved:", model_path)

# %%
import pandas as pd
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

train = pd.read_csv(
    BASE / "data/final/landslide_train.csv"
)

demographic_features = [
    "total_population",
    "children_0_14_ratio",
    "elderly_60_plus_ratio",
    "female_ratio",
    "unprotected_well_ratio",
    "no_toilet_ratio",
    "public_toilet_ratio"
]

rainfall_features = [
    "pre_rfh_1dekad",
    "pre_r1h",
    "pre_r3h",
    "pre_rfq",
    "pre_r1q",
    "pre_r3q"
]

feature_sets = {
    "Demographics": demographic_features,
    "Rainfall": rainfall_features,
    "Demographics + rainfall":
        demographic_features + rainfall_features
}

results = []

for name, features in feature_sets.items():

    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("classifier", RandomForestClassifier(
            n_estimators=300,
            max_depth=4,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1
        ))
    ])

    scores = cross_validate(
        model,
        train[features],
        train["risk_level"],
        groups=train["episode_id"],
        cv=GroupKFold(n_splits=5),
        scoring={
            "accuracy": "accuracy",
            "balanced_accuracy": "balanced_accuracy",
            "macro_f1": "f1_macro"
        },
        n_jobs=1
    )

    results.append({
        "Feature Set": name,
        "CV Accuracy": scores["test_accuracy"].mean(),
        "CV Balanced Accuracy":
            scores["test_balanced_accuracy"].mean(),
        "CV Macro F1": scores["test_macro_f1"].mean()
    })

comparison = pd.DataFrame(results)

print(
    comparison.sort_values(
        "CV Macro F1",
        ascending=False
    ).round(4).to_string(index=False)
)

# %%
import pandas as pd
from pathlib import Path

from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import GroupKFold, cross_validate
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

train = pd.read_csv(
    BASE / "data/final/landslide_train.csv"
)

features = [
    "total_population",
    "children_0_14_ratio",
    "elderly_60_plus_ratio",
    "female_ratio",
    "unprotected_well_ratio",
    "no_toilet_ratio",
    "public_toilet_ratio"
]

configs = [
    {"max_depth": 2, "min_samples_leaf": 2},
    {"max_depth": 3, "min_samples_leaf": 3},
    {"max_depth": 4, "min_samples_leaf": 3},
    {"max_depth": 4, "min_samples_leaf": 5},
    {"max_depth": 6, "min_samples_leaf": 3},
    {"max_depth": None, "min_samples_leaf": 5},
]

results = []

for config in configs:

    model = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("classifier", RandomForestClassifier(
            n_estimators=300,
            max_depth=config["max_depth"],
            min_samples_leaf=config["min_samples_leaf"],
            class_weight="balanced",
            random_state=42,
            n_jobs=-1
        ))
    ])

    scores = cross_validate(
        model,
        train[features],
        train["risk_level"],
        groups=train["episode_id"],
        cv=GroupKFold(n_splits=5),
        scoring={
            "accuracy": "accuracy",
            "balanced_accuracy": "balanced_accuracy",
            "macro_f1": "f1_macro"
        },
        n_jobs=1
    )

    results.append({
        **config,
        "CV Accuracy": scores["test_accuracy"].mean(),
        "CV Balanced Accuracy":
            scores["test_balanced_accuracy"].mean(),
        "CV Macro F1": scores["test_macro_f1"].mean()
    })

comparison = pd.DataFrame(results).sort_values(
    "CV Macro F1",
    ascending=False
)

print(comparison.round(4).to_string(index=False))

comparison.to_csv(
    BASE / "data/final/landslide_rf_tuning_results.csv",
    index=False
)

# %%
import pandas as pd
import joblib

from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix
)

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

train = pd.read_csv(BASE / "data/final/landslide_train.csv")
test = pd.read_csv(BASE / "data/final/landslide_test.csv")

features = [
    "total_population",
    "children_0_14_ratio",
    "elderly_60_plus_ratio",
    "female_ratio",
    "unprotected_well_ratio",
    "no_toilet_ratio",
    "public_toilet_ratio"
]

assert not (
    set(train["episode_id"]) & set(test["episode_id"])
), "Train/test episode overlap!"

model = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("classifier", RandomForestClassifier(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    ))
])

model.fit(train[features], train["risk_level"])

predictions = model.predict(test[features])

accuracy = accuracy_score(test["risk_level"], predictions)
balanced_accuracy = balanced_accuracy_score(
    test["risk_level"], predictions
)
macro_f1 = f1_score(
    test["risk_level"],
    predictions,
    average="macro"
)

print("LANDSLIDE — TEST RESULTS")
print("=" * 45)
print(f"Accuracy:          {accuracy:.4f}")
print(f"Balanced accuracy: {balanced_accuracy:.4f}")
print(f"Macro F1:          {macro_f1:.4f}")

print("\nClassification report:")
print(
    classification_report(
        test["risk_level"],
        predictions,
        zero_division=0
    )
)

labels = ["Low", "Moderate", "High", "Very High"]

print("\nConfusion matrix:")
print(
    pd.DataFrame(
        confusion_matrix(
            test["risk_level"],
            predictions,
            labels=labels
        ),
        index=[f"Actual {x}" for x in labels],
        columns=[f"Predicted {x}" for x in labels]
    )
)

model_path = BASE / "models/landslide_rf_tuned.joblib"

joblib.dump(
    {
        "model": model,
        "features": features,
        "target": "risk_level",
        "evaluation": {
            "accuracy": accuracy,
            "balanced_accuracy": balanced_accuracy,
            "macro_f1": macro_f1
        }
    },
    model_path
)

print("\nSaved:", model_path)

# %%
import pandas as pd
import joblib

from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    f1_score,
    classification_report,
    confusion_matrix
)

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

train = pd.read_csv(BASE / "data/final/landslide_train.csv")
test = pd.read_csv(BASE / "data/final/landslide_test.csv")

features = [
    "total_population",
    "children_0_14_ratio",
    "elderly_60_plus_ratio",
    "female_ratio",
    "unprotected_well_ratio",
    "no_toilet_ratio",
    "public_toilet_ratio"
]

assert not (
    set(train["episode_id"]) & set(test["episode_id"])
), "Train/test episode overlap!"

model = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("classifier", RandomForestClassifier(
        n_estimators=300,
        max_depth=4,
        min_samples_leaf=3,
        class_weight="balanced",
        random_state=42,
        n_jobs=-1
    ))
])

model.fit(train[features], train["risk_level"])

predictions = model.predict(test[features])

accuracy = accuracy_score(test["risk_level"], predictions)
balanced_accuracy = balanced_accuracy_score(
    test["risk_level"], predictions
)
macro_f1 = f1_score(
    test["risk_level"],
    predictions,
    average="macro"
)

print("LANDSLIDE — TEST RESULTS")
print("=" * 45)
print(f"Accuracy:          {accuracy:.4f}")
print(f"Balanced accuracy: {balanced_accuracy:.4f}")
print(f"Macro F1:          {macro_f1:.4f}")

print("\nClassification report:")
print(
    classification_report(
        test["risk_level"],
        predictions,
        zero_division=0
    )
)

labels = ["Low", "Moderate", "High", "Very High"]

print("\nConfusion matrix:")
print(
    pd.DataFrame(
        confusion_matrix(
            test["risk_level"],
            predictions,
            labels=labels
        ),
        index=[f"Actual {x}" for x in labels],
        columns=[f"Predicted {x}" for x in labels]
    )
)

model_path = BASE / "models/landslide_rf_tuned.joblib"

joblib.dump(
    {
        "model": model,
        "features": features,
        "target": "risk_level",
        "evaluation": {
            "accuracy": accuracy,
            "balanced_accuracy": balanced_accuracy,
            "macro_f1": macro_f1
        }
    },
    model_path
)

print("\nSaved:", model_path)

# %%
import joblib
import shap
import pandas as pd
import numpy as np
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")

for hazard in ["flood", "landslide"]:

    print("\n" + "=" * 55)
    print(f"{hazard.upper()} — SHAP VERIFICATION")
    print("=" * 55)

    saved = joblib.load(
        BASE / f"models/{hazard}_rf_tuned.joblib"
    )

    pipeline = saved["model"]
    features = saved["features"]

    test = pd.read_csv(
        BASE / f"data/final/{hazard}_test.csv"
    )

    X = test[features].head(5)

    # Apply the fitted preprocessing pipeline
    X_processed = pipeline.named_steps[
        "imputer"
    ].transform(X)

    classifier = pipeline.named_steps["classifier"]

    explainer = shap.TreeExplainer(classifier)
    shap_values = explainer(X_processed)

    predictions = pipeline.predict(X)

    print("Features:", len(features))
    print("Samples explained:", len(X))
    print("SHAP values shape:", shap_values.values.shape)
    print("Model classes:", classifier.classes_)
    print("Predictions:", predictions.tolist())

    # Verify the additive SHAP explanation for each
    # sample's predicted class.
    values = np.asarray(shap_values.values)
    base_values = np.asarray(shap_values.base_values)

    if values.ndim == 3:
        class_indices = [
            list(classifier.classes_).index(label)
            for label in predictions
        ]

        reconstructed = np.array([
            base_values[i, class_indices[i]]
            + values[i, :, class_indices[i]].sum()
            for i in range(len(X))
        ])

        predicted_probabilities = pipeline.predict_proba(X)

        actual = np.array([
            predicted_probabilities[i, class_indices[i]]
            for i in range(len(X))
        ])

        print(
            "Maximum SHAP reconstruction error:",
            np.max(np.abs(reconstructed - actual))
        )

print("\nSHAP verification completed.")

# %%



