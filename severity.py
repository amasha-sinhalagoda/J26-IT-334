"""
Landslide Severity Index (LSI): a first-draft 0-10 scale, distinct from the
raw ML occurrence probability.

Deliberately LINEAR, not logarithmic like the Richter scale: Richter's log
transform exists because seismic energy spans many orders of magnitude and
is derived from a physical wave-amplitude measurement. This prototype has no
equivalent physical quantity (no debris volume / runout data available), so
imposing a log scale on bounded [0,1] inputs would fabricate false
precision. A future version could adopt a log or power-law term once real
volumetric/energy-related data exists -- see notebook 03 for discussion.

LSI = 10 * clip(w_p*P_ml + w_r*Rainfall_norm + w_h*History_norm + w_s*Soil_weight, 0, 1)
"""

import numpy as np
import pandas as pd

from . import config


def rainfall_norm(max_24h_rainfall_mm) -> np.ndarray:
    """Piecewise-linear position on the NBRO scale itself:
    0 -> 0mm, 0.5 -> 100mm (Alert), 1.0 -> 150mm+ (Evacuation)."""
    x = np.asarray(max_24h_rainfall_mm, dtype=float)
    return np.clip(x / (2 * config.RAINFALL_ALERT_MM), 0.0, 1.0)


def history_norm(historical_failure_density_per_km2, ref_min=None, ref_max=None) -> np.ndarray:
    """Min-max normalize historical failure density. Pass ref_min/ref_max
    (e.g. from the training dataset) to keep new sites on the same scale;
    defaults to min/max of the input itself."""
    x = np.asarray(historical_failure_density_per_km2, dtype=float)
    lo = x.min() if ref_min is None else ref_min
    hi = x.max() if ref_max is None else ref_max
    if hi <= lo:
        return np.zeros_like(x)
    return np.clip((x - lo) / (hi - lo), 0.0, 1.0)


def compute_lsi(
    p_ml,
    max_24h_rainfall_mm,
    historical_failure_density_per_km2,
    soil_weight,
    hist_ref_min=None,
    hist_ref_max=None,
) -> np.ndarray:
    p_ml = np.asarray(p_ml, dtype=float)
    r_norm = rainfall_norm(max_24h_rainfall_mm)
    h_norm = history_norm(historical_failure_density_per_km2, hist_ref_min, hist_ref_max)
    s_w = np.asarray(soil_weight, dtype=float)

    composite = (
        config.LSI_WEIGHT_P_ML * p_ml
        + config.LSI_WEIGHT_RAINFALL * r_norm
        + config.LSI_WEIGHT_HISTORY * h_norm
        + config.LSI_WEIGHT_SOIL * s_w
    )
    return 10.0 * np.clip(composite, 0.0, 1.0)


def compute_lsi_breakdown(
    p_ml,
    max_24h_rainfall_mm,
    historical_failure_density_per_km2,
    soil_weight,
    hist_ref_min=None,
    hist_ref_max=None,
) -> pd.DataFrame:
    """Same as compute_lsi but returns the four weighted contributions
    (in LSI points, i.e. already *10) plus the final score and band --
    used for the per-site stacked-bar demonstration in notebook 03."""
    p_ml = np.asarray(p_ml, dtype=float)
    r_norm = rainfall_norm(max_24h_rainfall_mm)
    h_norm = history_norm(historical_failure_density_per_km2, hist_ref_min, hist_ref_max)
    s_w = np.asarray(soil_weight, dtype=float)

    contrib_p = 10.0 * config.LSI_WEIGHT_P_ML * p_ml
    contrib_r = 10.0 * config.LSI_WEIGHT_RAINFALL * r_norm
    contrib_h = 10.0 * config.LSI_WEIGHT_HISTORY * h_norm
    contrib_s = 10.0 * config.LSI_WEIGHT_SOIL * s_w

    raw_sum = contrib_p + contrib_r + contrib_h + contrib_s
    lsi = np.clip(raw_sum, 0.0, 10.0)
    band = [config.lsi_band(v) for v in lsi]

    return pd.DataFrame(
        {
            "contrib_p_ml": contrib_p,
            "contrib_rainfall": contrib_r,
            "contrib_history": contrib_h,
            "contrib_soil": contrib_s,
            "lsi": lsi,
            "lsi_band": band,
        }
    )
