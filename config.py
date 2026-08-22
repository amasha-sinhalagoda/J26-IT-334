"""
Central configuration for the Nuwara Eliya synthetic landslide prototype.

All value ranges below are ASSUMPTIONS grounded (where noted) in NBRO trigger
thresholds and general knowledge of the central highlands' geography/climate,
NOT measured data. Everything here is a first-draft constant, not a fitted
parameter -- treat this file as the single source of truth so notebooks 01-04
never drift out of sync with each other.
"""

import numpy as np

SEED = 42
N_PER_DIVISION = 150
DIVISIONS = ["Walapane", "Ambagamuwa", "Kotmale"]

# ---------------------------------------------------------------------------
# NBRO rainfall trigger thresholds (mm / 24h), from Landslide_Datasets_SriLanka.pdf
# ---------------------------------------------------------------------------
RAINFALL_WATCH_MM = 75
RAINFALL_ALERT_MM = 100
RAINFALL_EVACUATION_MM = 150


def rainfall_alert_level(max_24h_mm: float) -> str:
    if max_24h_mm >= RAINFALL_EVACUATION_MM:
        return "Evacuation"
    if max_24h_mm >= RAINFALL_ALERT_MM:
        return "Alert"
    if max_24h_mm >= RAINFALL_WATCH_MM:
        return "Watch"
    return "No Alert"


# Per-division rainfall climatology (assumption: Kotmale/Ambagamuwa windward
# and wetter, Walapane partial rain-shadow and drier).
RAINFALL_ANNUAL_MEAN_MM = {
    "Walapane": 2000,
    "Ambagamuwa": 2350,
    "Kotmale": 2400,
}
RAINFALL_ANNUAL_SD_MM = 300
RAINFALL_ANNUAL_BOUNDS = (1500, 3200)

# max_24h_rainfall_mm generated from a right-skewed distribution per division
# (Gamma), shape/scale chosen so a realistic tail crosses the NBRO thresholds.
MAX_24H_GAMMA_SHAPE = {
    "Walapane": 2.2,
    "Ambagamuwa": 2.6,
    "Kotmale": 2.8,
}
MAX_24H_GAMMA_SCALE_MM = 28  # mean ~= shape * scale

# ---------------------------------------------------------------------------
# NBRO slope risk bands (degrees), anchored at 11-16=Low and >35=Very High
# ---------------------------------------------------------------------------
SLOPE_BANDS = [
    (0, 11, "Very Low"),
    (11, 17, "Low"),
    (17, 26, "Moderate"),
    (26, 36, "High"),
    (36, 91, "Very High"),
]


def slope_band(slope_deg: float) -> str:
    for lo, hi, label in SLOPE_BANDS:
        if lo <= slope_deg < hi:
            return label
    return "Very High"


# Per-division slope climatology (assumption: Kotmale/Ambagamuwa steeper
# estate/valley terrain, Walapane comparatively moderate relief).
SLOPE_MEAN_DEG = {
    "Walapane": 21,
    "Ambagamuwa": 27,
    "Kotmale": 29,
}
SLOPE_SD_DEG = {
    "Walapane": 8,
    "Ambagamuwa": 9,
    "Kotmale": 9,
}
SLOPE_BOUNDS_DEG = (3, 55)

# ---------------------------------------------------------------------------
# Soil type: Red-Yellow Podzolic named explicitly as the Nuwara Eliya /
# Badulla / Kandy "clay-trap" soil in Landslide_Datasets_SriLanka.pdf.
# Susceptibility weights are author-assigned, not measured.
# ---------------------------------------------------------------------------
SOIL_TYPES = {
    "Red-Yellow Podzolic": 0.75,
    "Mountain Regosol": 0.60,
    "Reddish-Brown Latosolic": 0.35,
}

# Per-division category probabilities, must sum to 1 for each division.
SOIL_MIX = {
    "Walapane": {"Red-Yellow Podzolic": 0.35, "Mountain Regosol": 0.25, "Reddish-Brown Latosolic": 0.40},
    "Ambagamuwa": {"Red-Yellow Podzolic": 0.40, "Mountain Regosol": 0.40, "Reddish-Brown Latosolic": 0.20},
    "Kotmale": {"Red-Yellow Podzolic": 0.45, "Mountain Regosol": 0.35, "Reddish-Brown Latosolic": 0.20},
}

# ---------------------------------------------------------------------------
# Historical landslide record generation
# ---------------------------------------------------------------------------
SITE_CATCHMENT_AREA_KM2 = 1.0
HISTORICAL_YEARS = 20
HISTORICAL_MAX_COUNT = 10
# log-lambda regression coefficients for the Poisson count mean, driven by
# slope risk, soil weight, and the latent factor L (see labeling.py).
HIST_COEF_INTERCEPT = -1.6
HIST_COEF_SLOPE_RISK = 1.4
HIST_COEF_SOIL_WEIGHT = 1.1
HIST_COEF_LATENT = 1.6

# ---------------------------------------------------------------------------
# Latent ground-truth hazard function (labeling.py) -- these weights define
# the "true" data-generating process used to test, not assume, whether
# Feature Set A (soil+rainfall+history) or B (soil+rainfall+slope) is more
# predictive. Fixed BEFORE looking at any model results; do not retune after.
# ---------------------------------------------------------------------------
HAZARD_WEIGHT_SLOPE = 0.30
HAZARD_WEIGHT_SOIL = 0.20
HAZARD_WEIGHT_RAINFALL = 0.30
HAZARD_WEIGHT_LATENT = 0.20
HAZARD_NOISE_SD = 0.06
TARGET_PREVALENCE = 0.22  # roughly realistic rare-event class balance
HAZARD_SIGMOID_STEEPNESS = 10.0

RAINFALL_TERM_CENTER_MM = RAINFALL_ALERT_MM  # sigmoid centered on the NBRO Alert threshold
RAINFALL_TERM_SCALE_MM = 25.0

# ---------------------------------------------------------------------------
# Landslide Severity Index (LSI) -- first-draft linear 0-10 composite.
# Weights sum to 1; deliberately NOT a Richter-style log scale (see
# notebook 03 for the rationale: no physical energy/volume data available).
# ---------------------------------------------------------------------------
LSI_WEIGHT_P_ML = 0.45
LSI_WEIGHT_RAINFALL = 0.25
LSI_WEIGHT_HISTORY = 0.20
LSI_WEIGHT_SOIL = 0.10

LSI_BANDS = [
    (0.0, 2.5, "Negligible"),
    (2.5, 4.0, "Minor"),
    (4.0, 6.0, "Moderate"),
    (6.0, 8.0, "Major"),
    (8.0, 10.01, "Severe/Critical"),
]


def lsi_band(lsi: float) -> str:
    for lo, hi, label in LSI_BANDS:
        if lo <= lsi < hi:
            return label
    return "Severe/Critical"


def make_rng(seed: int = SEED) -> np.random.Generator:
    return np.random.default_rng(seed)
