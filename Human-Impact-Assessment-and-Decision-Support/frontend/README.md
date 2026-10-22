
  Human Impact Assessment and Decision Support

This component is part of a multi-hazard disaster management research project focused on flood and landslide impacts in Sri Lanka.

The component combines historical disaster impact records, demographic data, machine learning, and scenario-based decision support to assess potential human impact at Divisional Secretariat (DS) level.

   Implemented Features

1. Human Impact Classification and Explainability

Random Forest and XGBoost models were evaluated to classify historical affected-population magnitude into four categories: Low, Moderate, High, and Very High.

The implemented prediction service uses demographic indicators and provides:
- Predicted human impact category
- Model confidence and class probabilities
- SHAP explanations for individual predictions

2. Multi-Hazard Assessment and Decision Support

The decision-support engine combines flood and landslide severity inputs with population exposure, sensitivity, and response capacity.

It supports scenario-based assessment, division-level prioritization, and recommendations. Hazard severity values can be provided manually for independent testing or supplied by other components during system integration.

    Technologies

- Python, FastAPI
- scikit-learn, XGBoost, SHAP
- pandas, NumPy
- React, Vite
- GeoJSON and GIS datasets
- Jupyter Notebook

    Repository Structure

- api/ - FastAPI backend
- src/ - Prediction and decision-support implementation
- frontend/ - React dashboard
- models/ - Trained human impact classification models
- data/ - Prepared datasets and evaluation results
- notebooks/ - Data analysis and model development
- gis/ - Geographic boundaries
- outputs/ - Evaluation and demonstration outputs
- docs/ - Supporting documentation

    Backend API

| Method | Endpoint          |                  Purpose                              |
|--------|-------------------|-------------------------------------------------------|
| GET    | `/api/health`     | Backend health check                                  |
| POST   | `/api/ml/predict` | Human impact classification and SHAP explanations     |
| POST   | `/api/analyze`    | Multi-hazard scenario assessment and decision support |

     Running the Backend

Use a Python environment with the required project dependencies installed.

From this component's directory:

```bash
python -m uvicorn api.main:app --host 127.0.0.1 --port 8000 --reload