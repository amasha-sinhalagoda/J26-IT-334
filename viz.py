"""Shared plot styling so the 4 notebooks look like one consistent report."""

import matplotlib.pyplot as plt
import seaborn as sns

DIVISION_COLORS = {
    "Walapane": "#2E86AB",
    "Ambagamuwa": "#E67E22",
    "Kotmale": "#27AE60",
}

FEATURE_SET_COLORS = {
    "Set A (soil+rainfall+history)": "#8E44AD",
    "Set B (soil+rainfall+slope)": "#C0392B",
}

BAND_COLORS = {
    "Negligible": "#2ECC71",
    "Minor": "#A9DFBF",
    "Moderate": "#F4D03F",
    "Major": "#E67E22",
    "Severe/Critical": "#C0392B",
}


def set_style():
    sns.set_theme(style="whitegrid", context="notebook")
    plt.rcParams["figure.dpi"] = 110
    plt.rcParams["axes.titleweight"] = "bold"
    plt.rcParams["axes.titlesize"] = 12
