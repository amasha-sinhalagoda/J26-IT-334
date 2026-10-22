from dataclasses import dataclass


@dataclass
class InfrastructureAsset:
    name: str
    asset_type: str
    exposure: float
    vulnerability: float
    criticality: float


def assess_infrastructure(assets, hazard_severity):

    if not 0 <= hazard_severity <= 1:
        raise ValueError("Hazard severity must be between 0 and 1.")

    results = []

    for asset in assets:

        for field in ["exposure", "vulnerability", "criticality"]:
            value = getattr(asset, field)

            if not 0 <= value <= 1:
                raise ValueError(
                    f"{asset.name}: {field} must be between 0 and 1."
                )

        # Provisional infrastructure priority formula.
        risk_score = (
            0.35 * hazard_severity
            + 0.30 * asset.exposure
            + 0.20 * asset.vulnerability
            + 0.15 * asset.criticality
        )

        if risk_score >= 0.75:
            level = "Very High"
        elif risk_score >= 0.55:
            level = "High"
        elif risk_score >= 0.35:
            level = "Moderate"
        else:
            level = "Low"

        results.append({
            "name": asset.name,
            "asset_type": asset.asset_type,
            "risk_score": round(risk_score, 4),
            "risk_level": level,
            "scenario_type": "Provisional demonstration",
            "operational_warning": False
        })

    return sorted(
        results,
        key=lambda item: item["risk_score"],
        reverse=True
    )


if __name__ == "__main__":

    sample_assets = [
        InfrastructureAsset(
            "Example Hospital", "Hospital",
            exposure=0.9,
            vulnerability=0.6,
            criticality=1.0
        ),
        InfrastructureAsset(
            "Example School", "School",
            exposure=0.6,
            vulnerability=0.5,
            criticality=0.7
        ),
        InfrastructureAsset(
            "Example Bridge", "Bridge",
            exposure=0.8,
            vulnerability=0.8,
            criticality=0.9
        ),
        InfrastructureAsset(
            "Example Shelter", "Shelter",
            exposure=0.4,
            vulnerability=0.3,
            criticality=0.9
        )
    ]

    results = assess_infrastructure(
        sample_assets,
        hazard_severity=0.9
    )

    print("\nINFRASTRUCTURE RISK ASSESSMENT")

    for item in results:
        print(
            f"{item['name']}: "
            f"{item['risk_level']} "
            f"({item['risk_score']:.3f})"
        )