"""
Latent ground-truth hazard function -> binary landslide label.

This is the mechanism that makes the Feature-Set-A-vs-B comparison in
notebook 02 an honest test rather than a foregone conclusion. The label is
generated from slope, soil, rainfall, and a LATENT factor L that is never
exposed as a usable model feature -- Feature Set B (soil+rainfall+slope)
sees slope/soil/rainfall directly but is blind to L; Feature Set A
(soil+rainfall+history) sees soil/rainfall directly and only recovers a
noisy, indirect view of L through the historical failure count. Which set
wins is genuinely undetermined until the models are actually trained.

The weights below (config.HAZARD_WEIGHT_*) are fixed BEFORE inspecting any
model results. Retuning them after seeing which feature set "wins" would
rig the comparison and must not be done.
"""

import numpy as np
import pandas as pd

from . import config


def rainfall_term(max_24h_rainfall_mm) -> np.ndarray:
    x = np.asarray(max_24h_rainfall_mm, dtype=float)
    z = (x - config.RAINFALL_TERM_CENTER_MM) / config.RAINFALL_TERM_SCALE_MM
    return 1.0 / (1.0 + np.exp(-z))


def true_hazard_z(df: pd.DataFrame, rng: np.random.Generator) -> np.ndarray:
    rterm = rainfall_term(df["max_24h_rainfall_mm"])
    noise = rng.normal(0, config.HAZARD_NOISE_SD, size=len(df))
    z = (
        config.HAZARD_WEIGHT_SLOPE * df["slope_risk"].to_numpy()
        + config.HAZARD_WEIGHT_SOIL * df["soil_weight"].to_numpy()
        + config.HAZARD_WEIGHT_RAINFALL * rterm
        + config.HAZARD_WEIGHT_LATENT * df["latent_l"].to_numpy()
        + noise
    )
    return z


def calibrate_threshold(z: np.ndarray, k: float, target_prevalence: float) -> float:
    """Bisect for the threshold t such that mean(sigmoid(k*(z-t))) == target_prevalence.

    A quantile-of-z threshold does NOT hit the target exactly once the sigmoid
    blurs the boundary (points on the "wrong" side of a hard cutoff still have
    non-trivial probability), so the expected-value itself is calibrated
    directly instead. mean(sigmoid(...)) is monotonically decreasing in t, so
    plain bisection is stable.
    """
    lo, hi = float(z.min()) - 5.0, float(z.max()) + 5.0
    for _ in range(60):
        mid = (lo + hi) / 2.0
        prob_mean = (1.0 / (1.0 + np.exp(-k * (z - mid)))).mean()
        if prob_mean > target_prevalence:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def add_labels(df: pd.DataFrame, seed: int = config.SEED) -> pd.DataFrame:
    """Adds true_hazard_z, hazard_probability, and landslide_occurred columns.

    Threshold is calibrated so the *expected* proportion of positive labels
    matches config.TARGET_PREVALENCE; the sigmoid steepness then adds
    realistic label noise around that threshold rather than a hard cutoff.
    """
    rng = config.make_rng(seed + 1)  # separate stream from feature generation
    df = df.copy()
    z = true_hazard_z(df, rng)
    threshold = calibrate_threshold(z, config.HAZARD_SIGMOID_STEEPNESS, config.TARGET_PREVALENCE)
    prob = 1.0 / (1.0 + np.exp(-config.HAZARD_SIGMOID_STEEPNESS * (z - threshold)))
    label = rng.binomial(1, prob)

    df["true_hazard_z"] = z
    df["hazard_probability"] = prob
    df["landslide_occurred"] = label
    return df
