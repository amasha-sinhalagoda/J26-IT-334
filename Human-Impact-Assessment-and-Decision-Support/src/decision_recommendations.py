
from datetime import datetime, timezone


PRIORITY_ORDER = {
    "Low": 0,
    "Moderate": 1,
    "High": 2,
    "Very High": 3,
}


def generate_recommendations(analysis):
    """
    Generate provisional decision-support recommendations.

    This module does not issue real emergency warnings.
    """

    district = analysis["district"]
    division = analysis["division"]

    priority = analysis["decision_priority"]
    priority_level = priority["priority_level"]

    infrastructure = analysis.get(
        "infrastructure_risk", []
    )

    model_predictions = analysis.get(
        "model_predictions", {}
    )

    overlapping = priority["overlapping_hazards"]

    recommendations = []

    # ---------------------------------------
    # 1. DIVISION-LEVEL RECOMMENDATIONS
    # ---------------------------------------

    if priority_level == "Very High":
        recommendations.extend([
            "Prioritize this DS division for further assessment.",
            "Request verification of current conditions from "
            "authorized disaster-management agencies.",
            "Review emergency response resources and "
            "potential shelter availability.",
        ])

    elif priority_level == "High":
        recommendations.extend([
            "Schedule a priority review of the DS division.",
            "Check the availability of emergency response resources.",
        ])

    elif priority_level == "Moderate":
        recommendations.extend([
            "Continue reviewing hazard and vulnerability indicators.",
            "Check whether additional local data are available.",
        ])

    else:
        recommendations.append(
            "Maintain routine data review and monitoring."
        )

    # ---------------------------------------
    # 2. OVERLAPPING HAZARD RECOMMENDATIONS
    # ---------------------------------------

    if overlapping:
        recommendations.append(
            "Review possible combined flood and landslide "
            "exposure using verified hazard information."
        )

    # ---------------------------------------
    # 3. INFRASTRUCTURE RECOMMENDATIONS
    # ---------------------------------------

    critical_assets = [
        asset for asset in infrastructure
        if asset["risk_level"] in ("High", "Very High")
    ]

    for asset in critical_assets:

        asset_type = asset["asset_type"].lower()
        asset_name = asset["name"]

        if asset_type == "hospital":
            action = (
                f"Review accessibility, backup services, "
                f"and continuity plans for {asset_name}."
            )

        elif asset_type == "bridge":
            action = (
                f"Request a condition and access review "
                f"for {asset_name}."
            )

        elif asset_type == "school":
            action = (
                f"Review student safety and emergency "
                f"arrangements for {asset_name}."
            )

        elif asset_type == "shelter":
            action = (
                f"Verify accessibility, suitability, "
                f"and available capacity of {asset_name}."
            )

        else:
            action = (
                f"Review infrastructure conditions "
                f"for {asset_name}."
            )

        recommendations.append(action)

    # ---------------------------------------
    # 4. PROVISIONAL ALERT GRADING
    # ---------------------------------------

    alert_grades = {
        "Low": "INFORMATION",
        "Moderate": "ADVISORY",
        "High": "PRIORITY REVIEW",
        "Very High": "URGENT REVIEW",
    }

    alert_grade = alert_grades[priority_level]

    # ML predictions are shown as supporting
    # experimental results, not official warnings.
    prediction_summary = {
        hazard: {
            "impact_class": result["predicted_impact"],
            "predicted_class_probability": round(
                result["confidence"], 4
            ),
        }
        for hazard, result in model_predictions.items()
    }

    alert_message = (
        f"RESEARCH DEMONSTRATION ONLY — NOT AN OFFICIAL WARNING. "
        f"{alert_grade}: {division} DS Division, "
        f"{district} District. "
        f"Provisional decision priority: {priority_level} "
        f"(score {priority['priority_score']:.3f}). "
        f"Verify conditions with authorized agencies "
        f"before taking operational action."
    )

    return {
        "district": district,
        "division": division,
        "priority_level": priority_level,
        "alert_grade": alert_grade,
        "alert_message": alert_message,
        "recommendations": recommendations,
        "critical_infrastructure_count": len(
            critical_assets
        ),
        "experimental_model_predictions": prediction_summary,
        "generated_at_utc": datetime.now(
            timezone.utc
        ).isoformat(),
        "scenario_type": "Provisional research demonstration",
        "operational_warning": False,
        "notification_sent": False,
    }


if __name__ == "__main__":

    from src.decision_support_engine import (
        DecisionSupportEngine
    )

    from src.infrastructure_risk import (
        InfrastructureAsset
    )

    demographics = {
        "total_population": 50000,
        "children_0_14_ratio": 0.22,
        "elderly_60_plus_ratio": 0.12,
        "female_ratio": 0.52,
        "unprotected_well_ratio": 0.10,
        "no_toilet_ratio": 0.04,
        "public_toilet_ratio": 0.02,
    }

    assets = [
        InfrastructureAsset(
            "Example Hospital",
            "Hospital",
            0.9, 0.6, 1.0
        ),
        InfrastructureAsset(
            "Example Bridge",
            "Bridge",
            0.8, 0.8, 0.9
        ),
        InfrastructureAsset(
            "Example School",
            "School",
            0.6, 0.5, 0.7
        ),
        InfrastructureAsset(
            "Example Shelter",
            "Shelter",
            0.4, 0.3, 0.9
        ),
    ]

    engine = DecisionSupportEngine()

    analysis = engine.analyze(
        district="Colombo",
        division="Kaduwela",
        demographics=demographics,
        flood_severity=0.8,
        landslide_severity=0.6,
        exposure=0.7,
        sensitivity=0.65,
        response_capacity=0.4,
        infrastructure_assets=assets,
    )

    result = generate_recommendations(analysis)

    print("\n====================================")
    print("DECISION RECOMMENDATIONS AND ALERTS")
    print("====================================")

    print("\nDS Division:", result["division"])
    print("Priority:", result["priority_level"])
    print("Alert Grade:", result["alert_grade"])

    print("\n--- DEMONSTRATION ALERT ---")
    print(result["alert_message"])

    print("\n--- RECOMMENDED ACTIONS ---")

    for number, recommendation in enumerate(
        result["recommendations"], start=1
    ):
        print(f"{number}. {recommendation}")

    print("\nCritical infrastructure flagged:",
          result["critical_infrastructure_count"])

    print("Operational warning:",
          result["operational_warning"])

    print("Notification sent:",
          result["notification_sent"])

    print("\nRecommendation generation completed.")
