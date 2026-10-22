import pandas as pd

from src.human_impact_predictor import HumanImpactPredictor


class MultiHazardIntegration:

    def __init__(self):
        self.predictors = {
            "flood": HumanImpactPredictor("flood"),
            "landslide": HumanImpactPredictor("landslide")
        }

    def predict(self, hazard_inputs):
        """
        hazard_inputs example:
        {
            "flood": {
                "total_population": 50000,
                "children_0_14_ratio": 0.22,
                ...
            },
            "landslide": {
                "total_population": 50000,
                ...
            }
        }
        """

        results = {}

        for hazard, input_data in hazard_inputs.items():

            if hazard not in self.predictors:
                raise ValueError(
                    f"Unsupported hazard: {hazard}"
                )

            results[hazard] = self.predictors[
                hazard
            ].predict(input_data)

        return results


if __name__ == "__main__":
    system = MultiHazardIntegration()

    example = {
        "flood": {
            "total_population": 50000,
            "children_0_14_ratio": 0.22,
            "elderly_60_plus_ratio": 0.12,
            "female_ratio": 0.52,
            "unprotected_well_ratio": 0.10,
            "no_toilet_ratio": 0.04,
            "public_toilet_ratio": 0.02
        },
        "landslide": {
            "total_population": 50000,
            "children_0_14_ratio": 0.22,
            "elderly_60_plus_ratio": 0.12,
            "female_ratio": 0.52,
            "unprotected_well_ratio": 0.10,
            "no_toilet_ratio": 0.04,
            "public_toilet_ratio": 0.02
        }
    }

    results = system.predict(example)

    for hazard, result in results.items():
        print(
            hazard,
            result["predicted_impact"],
            result["confidence"]
        )