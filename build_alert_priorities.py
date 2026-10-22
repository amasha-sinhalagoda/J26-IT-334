from pathlib import Path

import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "processed_data"
ALERTS_FILE = DATA_DIR / "alerts_clean.csv"
POPULATION_FILE = DATA_DIR / "gn_population_5_districts_clean.csv"

SEVERITY_SCORES = {
    "critical": 1.00,
    "high": 0.75,
    "medium": 0.50,
    "low": 0.25,
}
WEIGHTS = {
    "severity_score": 0.50,
    "exposure_score": 0.30,
    "vulnerability_score": 0.20,
}


def normalize_key(series):
    return series.astype("string").str.strip().str.casefold()


def main():
    if not ALERTS_FILE.exists() or not POPULATION_FILE.exists():
        raise FileNotFoundError(
            "Run preprocess_dispatch.py first to create the cleaned input files"
        )

    requests = pd.read_csv(ALERTS_FILE)
    population = pd.read_csv(POPULATION_FILE)

    alert_fields = [
        "alert_id", "timestamp", "hazard_type", "severity", "confidence",
        "district", "DS_division", "GN_division", "latitude", "longitude",
        "affected_population", "affected_households",
    ]
    inconsistent = requests.groupby("alert_id")[alert_fields[1:]].nunique(
        dropna=False
    ).gt(1).any(axis=1)
    if inconsistent.any():
        bad_ids = inconsistent[inconsistent].index.tolist()
        raise ValueError(
            "Alert-level fields disagree across request rows: {}".format(bad_ids)
        )

    alerts = requests[alert_fields].drop_duplicates("alert_id").copy()
    alerts["_district_key"] = normalize_key(alerts["district"])
    alerts["_ds_key"] = normalize_key(alerts["DS_division"])
    alerts["_gn_key"] = normalize_key(alerts["GN_division"])

    population_fields = [
        "district_name", "ds_division_name", "gn_division_name", "age_total",
        "age_0_14", "age_65_and_above",
    ]
    population = population[population_fields].copy()
    population["_district_key"] = normalize_key(population["district_name"])
    population["_ds_key"] = normalize_key(population["ds_division_name"])
    population["_gn_key"] = normalize_key(population["gn_division_name"])

    location_keys = ["_district_key", "_ds_key", "_gn_key"]
    alert_locations = alerts[location_keys].drop_duplicates()
    population_for_alerts = population.merge(
        alert_locations, on=location_keys, how="inner"
    )
    duplicate_population_keys = population_for_alerts.duplicated(
        location_keys, keep=False
    )
    if duplicate_population_keys.any():
        examples = population_for_alerts.loc[
            duplicate_population_keys,
            ["district_name", "ds_division_name", "gn_division_name"],
        ].head(10)
        raise ValueError(
            "Alert locations have duplicate population keys:\n{}".format(examples)
        )
    if len(population_for_alerts) != len(alert_locations):
        matched_locations = population_for_alerts[location_keys].drop_duplicates()
        unmatched_locations = alert_locations.merge(
            matched_locations, on=location_keys, how="left", indicator=True
        )
        unmatched_locations = unmatched_locations[
            unmatched_locations["_merge"] == "left_only"
        ]
        raise ValueError(
            "Population records missing for alert location(s):\n{}".format(
                unmatched_locations
            )
        )

    for column in ["age_total", "age_0_14", "age_65_and_above"]:
        population[column] = pd.to_numeric(population[column], errors="coerce")

    if population[["age_total", "age_0_14", "age_65_and_above"]].isna().any().any():
        raise ValueError("Population age fields contain missing or nonnumeric values")
    if (population["age_total"] <= 0).any():
        raise ValueError("Population age_total must be greater than zero")
    if (
        population["age_0_14"] + population["age_65_and_above"]
        > population["age_total"]
    ).any():
        raise ValueError("Vulnerable age-group counts exceed total population")

    alerts["severity_score"] = (
        alerts["severity"].astype("string").str.strip().str.casefold()
        .map(SEVERITY_SCORES)
    )
    if alerts["severity_score"].isna().any():
        unknown = sorted(alerts.loc[alerts["severity_score"].isna(), "severity"].unique())
        raise ValueError("Unrecognized severity values: {}".format(unknown))

    alerts["affected_population"] = pd.to_numeric(
        alerts["affected_population"], errors="coerce"
    )
    if alerts["affected_population"].isna().any() or (
        alerts["affected_population"] < 0
    ).any():
        raise ValueError("Affected population must be present and nonnegative")

    alerts = alerts.merge(
        population_for_alerts[
            [
                "_district_key", "_ds_key", "_gn_key", "age_total",
                "age_0_14", "age_65_and_above",
            ]
        ],
        on=location_keys,
        how="left",
        validate="many_to_one",
        indicator=True,
    )
    unmatched = alerts["_merge"] != "both"
    if unmatched.any():
        records = alerts.loc[unmatched, ["district", "GN_division"]]
        raise ValueError(
            "No population match for alert area(s):\n{}".format(records)
        )
    alerts = alerts.drop(columns=["_merge", "_district_key", "_gn_key"])

    max_exposure = alerts["affected_population"].max()
    if max_exposure > 0:
        alerts["exposure_score"] = alerts["affected_population"] / max_exposure
    else:
        alerts["exposure_score"] = 0.0

    alerts["vulnerable_population_share"] = (
        alerts["age_0_14"] + alerts["age_65_and_above"]
    ) / alerts["age_total"]
    alerts["vulnerability_score"] = alerts["vulnerable_population_share"]
    alerts["priority_score"] = sum(
        alerts[column] * weight for column, weight in WEIGHTS.items()
    )
    alerts["priority_rank"] = alerts["priority_score"].rank(
        method="first", ascending=False
    ).astype(int)

    score_columns = [
        "alert_id", "district", "DS_division", "GN_division", "timestamp",
        "hazard_type", "severity", "confidence", "affected_population",
        "affected_households", "age_total", "age_0_14", "age_65_and_above",
        "vulnerable_population_share", "severity_score", "exposure_score",
        "vulnerability_score", "priority_score", "priority_rank",
    ]
    priority_scores = alerts[score_columns].sort_values(
        ["priority_rank", "alert_id"]
    )

    request_priorities = requests.merge(
        priority_scores[
            ["alert_id", "severity_score", "exposure_score",
             "vulnerability_score", "priority_score", "priority_rank"]
        ],
        on="alert_id",
        how="left",
        validate="many_to_one",
    )

    priority_scores.to_csv(
        DATA_DIR / "alert_priority_scores.csv", index=False, encoding="utf-8-sig"
    )
    request_priorities.to_csv(
        DATA_DIR / "alert_requests_prioritized.csv",
        index=False,
        encoding="utf-8-sig",
    )

    methodology = [
        "Prototype alert-priority scoring methodology",
        "One score is computed per unique alert; resource-type request rows inherit that score.",
        "Severity mapping: Critical=1.00, High=0.75, Medium=0.50, Low=0.25.",
        "Exposure score = affected_population / maximum affected_population in this alert batch.",
        "Vulnerability score = (GN population aged 0-14 + aged 65+) / GN total population.",
        "Priority score = 0.50*severity_score + 0.30*exposure_score + 0.20*vulnerability_score.",
        "This is a transparent prototype heuristic, not a trained or empirically validated model.",
        "Alert and resource records come from the supplied project datasets; GN population is provisional census data.",
        "The exposure score is batch-relative and may change when alerts are added or removed.",
    ]
    (DATA_DIR / "priority_scoring_methodology.txt").write_text(
        "\n".join(methodology), encoding="utf-8"
    )

    if len(priority_scores) != requests["alert_id"].nunique():
        raise ValueError("Priority output does not contain exactly one row per alert")
    if len(request_priorities) != len(requests) or request_priorities[
        "priority_score"
    ].isna().any():
        raise ValueError("Prioritized request output failed row-count or score checks")

    print("Priority scoring passed.")
    print("Unique alerts scored: {}".format(len(priority_scores)))
    print("All alerts matched to GN population: {}".format(len(priority_scores)))
    print("Prioritized outputs saved in: {}".format(DATA_DIR))
    print("Top five alerts:")
    print(
        priority_scores[
            ["priority_rank", "alert_id", "district", "GN_division", "priority_score"]
        ].head(5).to_string(index=False)
    )


if __name__ == "__main__":
    main()
