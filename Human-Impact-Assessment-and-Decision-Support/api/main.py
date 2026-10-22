
from functools import lru_cache

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from src.decision_support_engine import DecisionSupportEngine
from src.decision_recommendations import generate_recommendations
from src.ds_demographic_lookup import load_ds_demographics
from src.infrastructure_risk import InfrastructureAsset
from src.human_exposure_assessment import assess_human_exposure
from src.human_impact_predictor import HumanImpactPredictor


app = FastAPI(
    title="Multi-Hazard Human Impact & Decision Support API",
    description=(
        "Research API for flood and landslide human-impact "
        "assessment and decision support."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "message": "Multi-Hazard Decision Support API",
        "status": "running",
        "mode": "research_prototype",
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "service": "human_impact_decision_support",
        "ml_models_connected": False,
        "operational_warning_system": False,
    }


class AnalysisRequest(BaseModel):
    district: str = Field(min_length=1)
    division: str = Field(min_length=1)

    flood_severity: float | None = Field(
        default=None, ge=0, le=1
    )
    landslide_severity: float | None = Field(
        default=None, ge=0, le=1
    )

    exposure: float = Field(default=0.7, ge=0, le=1)
    sensitivity: float = Field(default=0.65, ge=0, le=1)
    response_capacity: float = Field(default=0.4, ge=0, le=1)

    exposed_fraction: float | None = Field(
        default=None, ge=0, le=1
    )

    include_example_infrastructure: bool = False


@lru_cache(maxsize=1)
def get_engine():
    return DecisionSupportEngine()


@lru_cache(maxsize=1)
def get_demographics():
    profiles_df, _profile_counts_df = load_ds_demographics()
    return profiles_df


def get_example_infrastructure():
    return [
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


@app.post("/api/analyze")
def analyze(request: AnalysisRequest):

    # Step 1: Validate selected hazards
    if (
        request.flood_severity is None
        and request.landslide_severity is None
    ):
        raise HTTPException(
            status_code=422,
            detail="Select at least one hazard.",
        )

    # Step 2: Load existing demographic profiles
    profiles_df = get_demographics()

    district_key = request.district.strip().casefold()
    division_key = request.division.strip().casefold()

    # Step 3: Find the selected DS Division
    matching_profiles = profiles_df.loc[
        (profiles_df["district_key"] == district_key)
        & (profiles_df["division_key"] == division_key)
    ]

    if matching_profiles.empty:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No demographic profile found for "
                f"{request.division}, {request.district}."
            ),
        )

    # Step 4: Convert the DataFrame row to a dictionary
    demographics = matching_profiles.iloc[0].to_dict()

    # Step 5: Optional fictional infrastructure for demonstration
    assets = (
        get_example_infrastructure()
        if request.include_example_infrastructure
        else []
    )

    # Step 6: Run the existing Python decision-support engine
    try:
        result = get_engine().analyze(
            district=request.district,
            division=request.division,
            demographics=demographics,
            flood_severity=request.flood_severity,
            landslide_severity=request.landslide_severity,
            exposure=request.exposure,
            sensitivity=request.sensitivity,
            response_capacity=request.response_capacity,
            infrastructure_assets=assets,
        )

        # Step 7: Generate situation-based recommendations
        recommendations = generate_recommendations(result)

        # Optional scenario-based human exposure estimate.
        human_exposure = None
        if request.exposed_fraction is not None:
            human_exposure = assess_human_exposure(
                district=request.district,
                division=request.division,
                exposed_fraction=request.exposed_fraction,
            )

        # Step 8: Historical human-impact ML predictions.
        # These models use demographics only, not scenario severity.
        model_features = [
            "total_population",
            "children_0_14_ratio",
            "elderly_60_plus_ratio",
            "female_ratio",
            "unprotected_well_ratio",
            "no_toilet_ratio",
            "public_toilet_ratio",
        ]

        ml_inputs = {
            feature: float(demographics[feature])
            for feature in model_features
        }

        source_hazards = str(
            demographics.get("source_hazard", "")
        ).strip().lower()

        supported_hazards = {
            hazard
            for hazard in ("flood", "landslide")
            if hazard in source_hazards
        }

        model_predictions = {}

        for hazard in ("flood", "landslide"):
            severity = getattr(request, f"{hazard}_severity")

            if severity is None or hazard not in supported_hazards:
                continue

            model_predictions[hazard] = (
                get_ml_predictor(hazard).predict(ml_inputs)
            )

        result["model_predictions"] = model_predictions

        # Step 9: Return the results to React
        return jsonable_encoder({
            "analysis": result,
            "decision_support": recommendations,
            "human_exposure": human_exposure,
            "data_source": "historical_demographics_manual_scenario",
            "operational_warning_system": False,
            "disclaimer": (
                "Research demonstration only. "
                "Not an official emergency warning."
            ),
        })

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {type(exc).__name__}: {exc}",
        ) from exc


# Historical human-impact ML classification.
# Separate from the scenario-based /api/analyze endpoint.

class MLPredictionRequest(BaseModel):
    hazard: str
    total_population: float = Field(ge=0)
    children_0_14_ratio: float = Field(ge=0, le=1)
    elderly_60_plus_ratio: float = Field(ge=0, le=1)
    female_ratio: float = Field(ge=0, le=1)
    unprotected_well_ratio: float = Field(ge=0, le=1)
    no_toilet_ratio: float = Field(ge=0, le=1)
    public_toilet_ratio: float = Field(ge=0, le=1)


@lru_cache(maxsize=2)
def get_ml_predictor(hazard: str):
    return HumanImpactPredictor(hazard)


@app.post("/api/ml/predict")
def predict_human_impact(request: MLPredictionRequest):
    hazard = request.hazard.strip().lower()

    if hazard not in ("flood", "landslide"):
        raise HTTPException(
            status_code=422,
            detail="Hazard must be 'flood' or 'landslide'.",
        )

    features = request.model_dump(exclude={"hazard"})

    try:
        predictor = get_ml_predictor(hazard)
        result = predictor.predict(features)

        return jsonable_encoder({
            **result,
            "prediction_type": "historical_human_impact_classification",
            "probability_calibrated": False,
            "operational_warning_system": False,
            "disclaimer": (
                "Research demonstration only. "
                "Demographic-only model; no event-specific "
                "hazard severity is included. "
                "Not an official disaster warning."
            ),
        })

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"ML prediction failed: "
                f"{type(exc).__name__}: {exc}"
            ),
        ) from exc
