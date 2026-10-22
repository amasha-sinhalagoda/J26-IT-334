from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import shap


BASE = Path(__file__).resolve().parents[1]

MODEL_FILES = {
    "flood": BASE / "models/flood_rf_tuned.joblib",
    "landslide": BASE / "models/landslide_rf_tuned.joblib",
}

FEATURE_NAMES = {
    "total_population": "Total population",
    "children_0_14_ratio": "Children aged 0–14",
    "elderly_60_plus_ratio": "Elderly population",
    "female_ratio": "Female population",
    "unprotected_well_ratio": "Unprotected wells",
    "no_toilet_ratio": "Households without toilets",
    "public_toilet_ratio": "Public toilet dependency",
}


class HumanImpactPredictor:

    def __init__(self, hazard):
        hazard = hazard.lower()

        if hazard not in MODEL_FILES:
            raise ValueError(
                "Hazard must be 'flood' or 'landslide'."
            )

        self.hazard = hazard

        saved = joblib.load(MODEL_FILES[hazard])

        self.pipeline = saved["model"]
        self.features = saved["features"]

        self.imputer = self.pipeline.named_steps["imputer"]
        self.classifier = self.pipeline.named_steps["classifier"]

        self.classes = list(self.classifier.classes_)

        self.explainer = shap.TreeExplainer(
            self.classifier
        )

    def predict(self, input_data):

        if isinstance(input_data, dict):
            input_data = pd.DataFrame([input_data])

        missing = [
            feature
            for feature in self.features
            if feature not in input_data.columns
        ]

        if missing:
            raise ValueError(
                f"Missing required features: {missing}"
            )

        X = input_data[self.features].copy()

        prediction = self.pipeline.predict(X)[0]

        probabilities = self.pipeline.predict_proba(X)[0]

        class_index = self.classes.index(prediction)

        X_processed = self.imputer.transform(X)

        explanation = self.explainer(X_processed)

        values = np.asarray(explanation.values)

        contributions = values[0, :, class_index]

        explanation_table = pd.DataFrame({
            "feature": self.features,
            "feature_name": [
                FEATURE_NAMES.get(f, f)
                for f in self.features
            ],
            "shap_value": contributions,
            "feature_value": X.iloc[0].values
        })

        explanation_table["absolute_contribution"] = (
            explanation_table["shap_value"].abs()
        )

        explanation_table = explanation_table.sort_values(
            "absolute_contribution",
            ascending=False
        )

        return {
            "hazard": self.hazard,
            "predicted_impact": prediction,
            "confidence": float(
                probabilities[class_index]
            ),
            "class_probabilities": {
                label: float(probability)
                for label, probability in zip(
                    self.classes,
                    probabilities
                )
            },
            "shap_explanation": (
                explanation_table.to_dict(
                    orient="records"
                )
            )
        }