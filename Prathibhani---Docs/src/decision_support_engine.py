
from src.multi_hazard_integration import MultiHazardIntegration
from src.multi_hazard_scoring import HazardInput, calculate_priority
from src.infrastructure_risk import (
    InfrastructureAsset,
    assess_infrastructure,
)


class DecisionSupportEngine:

    def __init__(self):
        self.predictor = MultiHazardIntegration()

    def analyze(
        self,
        district,
        division,
        demographics,
        flood_severity=None,
        landslide_severity=None,
        exposure=None,
        sensitivity=None,
        response_capacity=None,
        infrastructure_assets=None,
    ):

        if not district or not division:
            raise ValueError(
                "District and division are required."
            )

        if flood_severity is None and landslide_severity is None:
            raise ValueError(
                "At least one hazard severity is required."
            )

        if (
            exposure is None
            or sensitivity is None
            or response_capacity is None
        ):
            raise ValueError(
                "Exposure, sensitivity and response capacity are required."
            )

        # ---------------------------------------
        # STEP 1: HUMAN IMPACT ML PREDICTIONS
        # ---------------------------------------

        hazard_inputs = {}

        if flood_severity is not None:
            hazard_inputs["flood"] = demographics

        if landslide_severity is not None:
            hazard_inputs["landslide"] = demographics

        predictions = self.predictor.predict(
            hazard_inputs
        )

        # ---------------------------------------
        # STEP 2: MULTI-HAZARD PRIORITY SCORING
        # ---------------------------------------

        priority = calculate_priority(
            HazardInput(
                flood_severity=flood_severity,
                landslide_severity=landslide_severity,
                exposure=exposure,
                sensitivity=sensitivity,
                response_capacity=response_capacity,
            )
        )

        # ---------------------------------------
        # STEP 3: INFRASTRUCTURE RISK ASSESSMENT
        # ---------------------------------------

        infrastructure_results = []

        if infrastructure_assets is not None:

            hazard_severities = [
                value
                for value in [
                    flood_severity,
                    landslide_severity,
                ]
                if value is not None
            ]

            effective_hazard_severity = max(
                hazard_severities
            )

            infrastructure_results = assess_infrastructure(
                infrastructure_assets,
                hazard_severity=effective_hazard_severity,
            )

        # ---------------------------------------
        # STEP 4: COMBINED DECISION SUPPORT RESULT
        # ---------------------------------------

        return {
            "district": district,
            "division": division,
            "model_predictions": predictions,
            "decision_priority": priority,
            "infrastructure_risk": infrastructure_results,
            "model_scope": (
                "Experimental human-impact models use "
                "demographic features. Hazard severity "
                "is used for decision scoring, not as "
                "an input to the trained classifiers."
            ),
            "scenario_type": (
                "Provisional research demonstration"
            ),
            "operational_warning": False,
        }


# ============================================
# TEST THE COMPLETE DECISION SUPPORT ENGINE
# ============================================

if __name__ == "__main__":

    # Example demographic inputs
    demographics = {
        "total_population": 50000,
        "children_0_14_ratio": 0.22,
        "elderly_60_plus_ratio": 0.12,
        "female_ratio": 0.52,
        "unprotected_well_ratio": 0.10,
        "no_toilet_ratio": 0.04,
        "public_toilet_ratio": 0.02,
    }

    # Example infrastructure inputs
    infrastructure_assets = [
        InfrastructureAsset(
            name="Example Hospital",
            asset_type="Hospital",
            exposure=0.9,
            vulnerability=0.6,
            criticality=1.0,
        ),
        InfrastructureAsset(
            name="Example Bridge",
            asset_type="Bridge",
            exposure=0.8,
            vulnerability=0.8,
            criticality=0.9,
        ),
        InfrastructureAsset(
            name="Example School",
            asset_type="School",
            exposure=0.6,
            vulnerability=0.5,
            criticality=0.7,
        ),
        InfrastructureAsset(
            name="Example Shelter",
            asset_type="Shelter",
            exposure=0.4,
            vulnerability=0.3,
            criticality=0.9,
        ),
    ]

    # Initialize the system
    engine = DecisionSupportEngine()

    # Run integrated analysis
    result = engine.analyze(
        district="Colombo",
        division="Kaduwela",
        demographics=demographics,
        flood_severity=0.8,
        landslide_severity=0.6,
        exposure=0.7,
        sensitivity=0.65,
        response_capacity=0.4,
        infrastructure_assets=infrastructure_assets,
    )

    # ---------------------------------------
    # DISPLAY LOCATION
    # ---------------------------------------

    print("\n===================================")
    print("MULTI-HAZARD DECISION SUPPORT SYSTEM")
    print("===================================")

    print("\nDistrict:", result["district"])
    print("DS Division:", result["division"])

    # ---------------------------------------
    # DISPLAY ML PREDICTIONS
    # ---------------------------------------

    print("\n--- HUMAN IMPACT PREDICTIONS ---")

    for hazard, prediction in result[
        "model_predictions"
    ].items():

        print(
            f"{hazard.capitalize()}: "
            f"{prediction['predicted_impact']} "
            f"({prediction['confidence']:.2%})"
        )

    # ---------------------------------------
    # DISPLAY DECISION PRIORITY
    # ---------------------------------------

    print("\n--- MULTI-HAZARD PRIORITY ---")

    priority = result["decision_priority"]

    print(
        "Priority Score:",
        priority["priority_score"]
    )

    print(
        "Priority Level:",
        priority["priority_level"]
    )

    print(
        "Overlapping Hazards:",
        priority["overlapping_hazards"]
    )

    # ---------------------------------------
    # DISPLAY INFRASTRUCTURE RISK
    # ---------------------------------------

    print("\n--- INFRASTRUCTURE RISK ---")

    for asset in result["infrastructure_risk"]:

        print(
            f"{asset['name']} "
            f"({asset['asset_type']}): "
            f"{asset['risk_level']} "
            f"({asset['risk_score']:.3f})"
        )

    # ---------------------------------------
    # DISPLAY SYSTEM STATUS
    # ---------------------------------------

    print("\n--- SYSTEM STATUS ---")

    print("Scenario:", result["scenario_type"])

    print(
        "Operational Warning:",
        result["operational_warning"]
    )

    print("\nAnalysis completed successfully.")
