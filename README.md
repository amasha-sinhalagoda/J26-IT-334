# Nuwara Eliya Landslide ML Prototype

> **⚠️ SYNTHETIC DATA DISCLAIMER**
> Every dataset in this repository (`data/synthetic/nuwara_eliya_synthetic_sites.csv`) is
> **generated example data**, not a real observation. It stands in for datasets the
> researcher is still requesting from NBRO, the Survey Department, the Department of
> Agriculture, and the Department of Meteorology (see the sourcing checklist referenced
> below). Value ranges and rough relationships are anchored to published NBRO
> thresholds and general knowledge of Nuwara Eliya's climate/geography, but no
> conclusion drawn from this notebook set should be read as a real-world finding about
> landslide risk in Walapane, Ambagamuwa, or Kotmale until it is re-run on real data.

## What this is

A methodology prototype for the "Probabilistic Assessment and Forecasting of Landslide
Occurrences using Machine Learning" research component, scoped to three DS divisions in
Nuwara Eliya district: **Walapane, Ambagamuwa, Kotmale**. It exists to:

1. Generate literature-grounded synthetic sites (soil type, rainfall, slope angle,
   historical landslide records) for the three divisions.
2. Fairly test — not assume — whether **Feature Set A** (soil + rainfall + historical
   landslide data) or **Feature Set B** (soil + rainfall + slope/DEM) is more predictive
   of landslide occurrence, using the same models (XGBoost, LightGBM) on both.
3. Draft a first-version **Landslide Severity Index (LSI)**, a 0-10 scale (analogous in
   spirit to the Richter scale, but linear rather than logarithmic — see notebook 03 for
   why) that goes beyond a raw occurrence probability.
4. Explain individual predictions with SHAP, producing a real data-driven version of the
   illustrative Soil/History/Rainfall percentage split already shown on the live
   [component site](https://sadumina.github.io/Landlside-Suceptability-Component/).

## How to run

```bash
pip install -r requirements.txt
jupyter lab
```

Run the notebooks **in order** — each writes an artifact the next one depends on:

| Notebook | Produces |
|---|---|
| `01_data_generation_and_eda.ipynb` | `data/synthetic/nuwara_eliya_synthetic_sites.csv` |
| `02_model_comparison.ipynb` | Feature Set A vs B comparison, `outputs/models/best_model.joblib` |
| `03_severity_index.ipynb` | LSI demonstration on example sites |
| `04_shap_explainability.ipynb` | SHAP global + per-site breakdown charts |

Alternatively, execute headlessly:

```bash
jupyter nbconvert --to notebook --execute --inplace notebooks/01_data_generation_and_eda.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/02_model_comparison.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/03_severity_index.ipynb
jupyter nbconvert --to notebook --execute --inplace notebooks/04_shap_explainability.ipynb
```

## Project layout

```
src/landslide_toy/    # config, generators, labeling, severity index, plotting -- shared by all notebooks
notebooks/             # the 4-notebook pipeline described above
data/synthetic/        # generated CSV (not committed as "real" data)
data/raw/               # placeholder for real datasets once sourced
outputs/                # figures, tables, saved model
```

## Next step: swapping in real data

`src/landslide_toy/config.py` documents every assumed value range and its rationale. When
real datasets arrive, replace `data_generation.py`'s generators with loaders for the real
sources — the sourcing checklist for each factor (where to request it in Sri Lanka, format,
resolution) is already compiled in the research team's own
`Datasets.pdf` / `Landslide_Datasets_SriLanka.pdf` documents.
