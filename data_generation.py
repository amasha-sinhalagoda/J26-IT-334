"""
Synthetic feature generators for the Nuwara Eliya prototype.

Every value here is EXAMPLE / SYNTHETIC data standing in for real datasets
the researcher is still requesting from NBRO / Survey Department / Dept. of
Agriculture / Dept. of Meteorology. Ranges and relationships are anchored to
the NBRO thresholds and general highlands climatology documented in
config.py; nothing here should be read as a real measurement.
"""

import numpy as np
import pandas as pd

from . import config


def _truncated_normal(rng, mean, sd, low, high, size):
    out = rng.normal(mean, sd, size=size)
    return np.clip(out, low, high)


def generate_soil(division: str, n: int, rng: np.random.Generator) -> pd.Series:
    mix = config.SOIL_MIX[division]
    categories = list(mix.keys())
    probs = list(mix.values())
    return pd.Series(rng.choice(categories, size=n, p=probs), name="soil_type")


def generate_rainfall(division: str, n: int, rng: np.random.Generator) -> pd.DataFrame:
    annual = _truncated_normal(
        rng,
        config.RAINFALL_ANNUAL_MEAN_MM[division],
        config.RAINFALL_ANNUAL_SD_MM,
        *config.RAINFALL_ANNUAL_BOUNDS,
        size=n,
    )
    shape = config.MAX_24H_GAMMA_SHAPE[division]
    scale = config.MAX_24H_GAMMA_SCALE_MM
    max_24h = rng.gamma(shape, scale, size=n)
    max_24h = np.clip(max_24h, 5, 400)
    alert = [config.rainfall_alert_level(v) for v in max_24h]
    return pd.DataFrame(
        {
            "rainfall_annual_mm": annual,
            "max_24h_rainfall_mm": max_24h,
            "rainfall_alert_level": alert,
        }
    )


def generate_slope(division: str, n: int, rng: np.random.Generator) -> pd.DataFrame:
    slope_deg = _truncated_normal(
        rng,
        config.SLOPE_MEAN_DEG[division],
        config.SLOPE_SD_DEG[division],
        *config.SLOPE_BOUNDS_DEG,
        size=n,
    )
    band = [config.slope_band(v) for v in slope_deg]
    return pd.DataFrame({"slope_deg": slope_deg, "slope_band": band})


def slope_risk_from_deg(slope_deg) -> np.ndarray:
    """Map slope degrees to a 0-1 risk score, linear between the NBRO Low (11 deg)
    and Very High (35 deg) anchors, clipped outside that range."""
    return np.clip((np.asarray(slope_deg) - 10.0) / 30.0, 0.0, 1.0)


def generate_historical(
    slope_risk: np.ndarray, soil_weight: np.ndarray, latent_l: np.ndarray, rng: np.random.Generator
) -> pd.DataFrame:
    log_lambda = (
        config.HIST_COEF_INTERCEPT
        + config.HIST_COEF_SLOPE_RISK * slope_risk
        + config.HIST_COEF_SOIL_WEIGHT * soil_weight
        + config.HIST_COEF_LATENT * latent_l
    )
    lam = np.exp(log_lambda)
    count = rng.poisson(lam)
    count = np.clip(count, 0, config.HISTORICAL_MAX_COUNT)
    density = count / config.SITE_CATCHMENT_AREA_KM2

    # Recency: sites with more failures tend to have a more recent one too.
    # Uniform over the 20yr window, biased earlier (more "days since") when count is 0.
    days_window = config.HISTORICAL_YEARS * 365
    recency_bias = np.where(count > 0, 1.0, 4.0)
    days_since_last = rng.uniform(0, days_window, size=len(count)) / recency_bias
    days_since_last = np.where(count == 0, days_window, days_since_last)

    return pd.DataFrame(
        {
            "historical_failure_count_20yr": count,
            "historical_failure_density_per_km2": density,
            "days_since_last_failure": days_since_last,
        }
    )


def generate_sites(seed: int = config.SEED, n_per_division: int = config.N_PER_DIVISION) -> pd.DataFrame:
    """Generate the full synthetic site table for all three divisions.

    Returns a DataFrame with one row per synthetic site, including the
    latent factor L and true hazard Z used only for transparency/EDA -- the
    ML notebooks must not use latent_l or true_hazard_z as model features,
    since they are not observable in reality (labeling.py enforces this by
    only exposing the engineered feature columns).
    """
    rng = config.make_rng(seed)
    frames = []
    for division in config.DIVISIONS:
        n = n_per_division
        soil_type = generate_soil(division, n, rng)
        soil_weight = soil_type.map(config.SOIL_TYPES).to_numpy()
        rainfall_df = generate_rainfall(division, n, rng)
        slope_df = generate_slope(division, n, rng)
        slope_risk = slope_risk_from_deg(slope_df["slope_deg"])
        latent_l = rng.beta(2, 2, size=n)
        hist_df = generate_historical(slope_risk, soil_weight, latent_l, rng)

        df = pd.DataFrame(
            {
                "site_id": [f"{division[:3].upper()}-{i:04d}" for i in range(n)],
                "division": division,
                "soil_type": soil_type.to_numpy(),
                "soil_weight": soil_weight,
            }
        )
        df = pd.concat([df, rainfall_df, slope_df, hist_df], axis=1)
        df["slope_risk"] = slope_risk
        df["latent_l"] = latent_l  # kept for EDA/transparency only, not a model feature
        frames.append(df)

    sites = pd.concat(frames, ignore_index=True)
    sites = sites.sample(frac=1, random_state=seed).reset_index(drop=True)
    return sites
