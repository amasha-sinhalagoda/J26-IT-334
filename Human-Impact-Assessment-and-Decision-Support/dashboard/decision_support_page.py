
import sys
import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# ============================================
# PROJECT CONFIGURATION
# ============================================

BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.decision_support_engine import DecisionSupportEngine
from src.decision_recommendations import generate_recommendations
from src.infrastructure_risk import InfrastructureAsset
from src.ds_demographic_lookup import load_ds_demographics
from src.ds_hazard_inputs import (
    DSHazardInput,
    prepare_hazard_input,
)


st.set_page_config(
    page_title="Multi-Hazard Decision Support",
    page_icon="🌍",
    layout="wide",
)

st.title("Multi-Hazard Human Impact & Decision Support")

st.caption(
    "DS-level research demonstration integrating experimental "
    "human-impact prediction, vulnerability, infrastructure "
    "assessment, explainability and decision support."
)

st.warning(
    "RESEARCH DEMONSTRATION ONLY — NOT AN OFFICIAL DISASTER "
    "WARNING. Hazard severities and infrastructure scores "
    "are provisional scenario inputs."
)


# ============================================
# LOAD MODELS AND DEMOGRAPHICS
# ============================================

@st.cache_resource
def load_engine():
    return DecisionSupportEngine()


@st.cache_data
def get_demographic_lookup():
    lookup, _ = load_ds_demographics()
    return lookup


ds_lookup = get_demographic_lookup()


# ============================================
# SECTION 1 — SELECT DS DIVISION
# ============================================

st.header("1. Select DS Division")

district_options = sorted(
    ds_lookup["District"].dropna().unique().tolist()
)

district = st.selectbox(
    "Select District",
    district_options,
    key="analysis_district",
)

district_records = ds_lookup[
    ds_lookup["District"] == district
]

division_options = sorted(
    district_records["Division"].dropna().unique().tolist()
)

division = st.selectbox(
    "Select DS Division",
    division_options,
    key=f"analysis_division_{district}",
)

selected_ds = district_records[
    district_records["Division"] == division
].iloc[0]

st.success(
    f"Demographic profile loaded: {division}, {district}"
)

st.caption(
    "These demographic profiles come from prepared historical "
    "research datasets and are not verified current estimates."
)


# ============================================
# SECTION 2 — HAZARD SEVERITY
# ============================================

st.header("2. Hazard Severity Inputs")

st.caption(
    "Select applicable hazards and enter severity values "
    "between 0 and 1. These are manually supplied "
    "research scenarios, not live forecasts."
)

hazard_selection = st.multiselect(
    "Select Applicable Hazards",
    ["Flood", "Landslide"],
    default=["Flood", "Landslide"],
)

col1, col2 = st.columns(2)

with col1:
    flood_severity = (
        st.slider(
            "Flood Severity",
            min_value=0.0,
            max_value=1.0,
            value=0.8,
            step=0.05,
        )
        if "Flood" in hazard_selection
        else None
    )

with col2:
    landslide_severity = (
        st.slider(
            "Landslide Severity",
            min_value=0.0,
            max_value=1.0,
            value=0.6,
            step=0.05,
        )
        if "Landslide" in hazard_selection
        else None
    )


# ============================================
# SECTION 3 — AUTOMATIC DEMOGRAPHIC FEATURES
# ============================================

st.header("3. DS-Level Demographic Features")

demographics = {
    "total_population": int(
        selected_ds["total_population"]
    ),
    "children_0_14_ratio": float(
        selected_ds["children_0_14_ratio"]
    ),
    "elderly_60_plus_ratio": float(
        selected_ds["elderly_60_plus_ratio"]
    ),
    "female_ratio": float(
        selected_ds["female_ratio"]
    ),
    "unprotected_well_ratio": float(
        selected_ds["unprotected_well_ratio"]
    ),
    "no_toilet_ratio": float(
        selected_ds["no_toilet_ratio"]
    ),
    "public_toilet_ratio": float(
        selected_ds["public_toilet_ratio"]
    ),
}

demographic_df = pd.DataFrame(
    [
        {
            "Feature": key.replace("_", " ").title(),
            "Value": value,
        }
        for key, value in demographics.items()
    ]
)

st.dataframe(
    demographic_df,
    hide_index=True,
    width="stretch",
)


# ============================================
# SECTION 4 — DECISION-SUPPORT INDICATORS
# ============================================

st.header("4. Exposure, Sensitivity and Capacity")

st.caption(
    "These values are provisional manual scenario scores. "
    "They are not automatically derived from GIS or "
    "verified response-capacity datasets."
)

col1, col2, col3 = st.columns(3)

with col1:
    exposure = st.slider(
        "Exposure",
        0.0,
        1.0,
        0.7,
        0.05,
    )

with col2:
    sensitivity = st.slider(
        "Sensitivity",
        0.0,
        1.0,
        0.65,
        0.05,
    )

with col3:
    response_capacity = st.slider(
        "Response Capacity",
        0.0,
        1.0,
        0.4,
        0.05,
    )


# ============================================
# SECTION 5 — INFRASTRUCTURE
# ============================================

st.header("5. Infrastructure Risk Scenario")

st.caption(
    "The assets below are fictional examples with "
    "manually assigned exposure, vulnerability "
    "and criticality scores."
)

include_assets = st.checkbox(
    "Include Example Infrastructure",
    value=True,
)

infrastructure_assets = []

if include_assets:
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


# ============================================
# SECTION 6 — RUN INTEGRATED ANALYSIS
# ============================================

st.divider()

if st.button(
    "Run Multi-Hazard Analysis",
    type="primary",
    width="stretch",
):

    if not hazard_selection:
        st.error(
            "Select at least one hazard before running analysis."
        )

    else:
        try:
            hazard_input = DSHazardInput(
                district=district,
                division=division,
                flood_severity=flood_severity,
                landslide_severity=landslide_severity,
                source="manual_scenario",
            )

            prepared_input = prepare_hazard_input(
                hazard_input
            )

            engine = load_engine()

            # Use the validated interface if available.
            if hasattr(engine, "analyze_hazard_input"):
                analysis = engine.analyze_hazard_input(
                    hazard_input=hazard_input,
                    demographics=demographics,
                    exposure=exposure,
                    sensitivity=sensitivity,
                    response_capacity=response_capacity,
                    infrastructure_assets=infrastructure_assets,
                )

            else:
                # Compatibility with the existing engine.
                analysis = engine.analyze(
                    district=prepared_input["district"],
                    division=prepared_input["division"],
                    demographics=demographics,
                    flood_severity=prepared_input[
                        "flood_severity"
                    ],
                    landslide_severity=prepared_input[
                        "landslide_severity"
                    ],
                    exposure=exposure,
                    sensitivity=sensitivity,
                    response_capacity=response_capacity,
                    infrastructure_assets=infrastructure_assets,
                )

                analysis["hazard_input"] = prepared_input

            recommendations = generate_recommendations(
                analysis
            )

            # ====================================
            # STEP 36.3 — SAVE LATEST ANALYSIS
            # ====================================

            st.session_state["latest_analysis"] = analysis

            st.success("Analysis completed successfully.")

            st.header("Analysis Results")

            # ------------------------------------
            # MULTI-HAZARD PRIORITY
            # ------------------------------------

            priority = analysis["decision_priority"]

            c1, c2, c3 = st.columns(3)

            with c1:
                st.metric(
                    "Decision Priority",
                    priority["priority_level"],
                )

            with c2:
                st.metric(
                    "Priority Score",
                    f"{priority['priority_score']:.3f}",
                )

            with c3:
                st.metric(
                    "Overlapping Hazards",
                    (
                        "Yes"
                        if priority["overlapping_hazards"]
                        else "No"
                    ),
                )

            st.caption(
                "Priority is a provisional rule-based "
                "score. It is separate from the ML "
                "human-impact predictions."
            )

            # ------------------------------------
            # ML PREDICTIONS AND SHAP
            # ------------------------------------

            st.subheader("Human-Impact ML Predictions")

            for hazard, prediction in analysis[
                "model_predictions"
            ].items():

                st.markdown(
                    f"**{hazard.capitalize()}** — "
                    f"{prediction['predicted_impact']} "
                    f"(predicted-class probability: "
                    f"{prediction['confidence']:.2%})"
                )

                probability_df = pd.DataFrame(
                    [
                        {
                            "Impact class": name,
                            "Probability": probability,
                        }
                        for name, probability in prediction[
                            "class_probabilities"
                        ].items()
                    ]
                )

                st.bar_chart(
                    probability_df.set_index(
                        "Impact class"
                    )
                )

                with st.expander(
                    f"{hazard.capitalize()} SHAP Explanation"
                ):
                    shap_df = pd.DataFrame(
                        prediction["shap_explanation"]
                    )

                    st.dataframe(
                        shap_df[
                            [
                                "feature_name",
                                "feature_value",
                                "shap_value",
                            ]
                        ],
                        width="stretch",
                    )

                    st.caption(
                        "SHAP values explain contributions "
                        "to the predicted class probability. "
                        "They do not establish causation."
                    )

            # ------------------------------------
            # INFRASTRUCTURE RISK
            # ------------------------------------

            st.subheader("Infrastructure Risk Assessment")

            infrastructure_results = analysis[
                "infrastructure_risk"
            ]

            if infrastructure_results:
                infrastructure_df = pd.DataFrame(
                    infrastructure_results
                )

                st.dataframe(
                    infrastructure_df[
                        [
                            "name",
                            "asset_type",
                            "risk_score",
                            "risk_level",
                        ]
                    ],
                    width="stretch",
                )

            else:
                st.info(
                    "No infrastructure assets supplied."
                )

            # ------------------------------------
            # RECOMMENDATIONS
            # ------------------------------------

            st.subheader("Decision Recommendations")

            for number, action in enumerate(
                recommendations["recommendations"],
                start=1,
            ):
                st.write(f"{number}. {action}")

            # ------------------------------------
            # DEMONSTRATION ALERT
            # ------------------------------------

            st.subheader("Graded Demonstration Alert")

            st.info(
                recommendations["alert_message"]
            )

            st.caption(
                "No SMS or email notification was sent. "
                "This is not an operational warning."
            )

            # ------------------------------------
            # INPUT PROVENANCE
            # ------------------------------------

            with st.expander("Hazard Input Details"):
                st.json(analysis["hazard_input"])

        except Exception as error:
            st.error(f"Analysis failed: {error}")
            st.exception(error)


# ============================================
# SECTION 7 — GIS MAP
# ============================================

st.divider()

st.header("7. DS-Level GIS Priority Map")


# ============================================
# STEP 36.3 — CURRENT ANALYSIS RESULTS
# ============================================

latest_analysis = st.session_state.get(
    "latest_analysis"
)

if latest_analysis is not None:

    same_location = (
        latest_analysis["district"].strip().casefold()
        == district.strip().casefold()
        and latest_analysis["division"].strip().casefold()
        == division.strip().casefold()
    )

    if same_location:

        latest_priority = latest_analysis[
            "decision_priority"
        ]

        st.subheader("Current Multi-Hazard Scenario")

        col1, col2 = st.columns(2)

        with col1:
            st.metric(
                "Calculated Priority Level",
                latest_priority["priority_level"],
            )

        with col2:
            st.metric(
                "Calculated Priority Score",
                f"{latest_priority['priority_score']:.3f}",
            )

        st.caption(
            "This score was calculated from the latest "
            "manual hazard scenario for the selected "
            "DS division. It is not an official "
            "risk assessment."
        )

    else:
        st.info(
            "The latest analysis belongs to a different "
            "DS division. Run the analysis again to "
            "update the selected location."
        )

else:
    st.info(
        "Run Multi-Hazard Analysis to display the "
        "current scenario's priority score here."
    )


# ============================================
# EXISTING GIS DEMONSTRATION MAP
# ============================================

st.info(
    "The map below shows previously generated simulated "
    "flood-priority scores. Its polygon colors are not "
    "dynamically connected to the current analysis and "
    "do not represent a combined multi-hazard forecast."
)

GIS_FILE = (
    BASE_DIR
    / "outputs"
    / "gis"
    / "flood_ds_priority_map.geojson"
)


@st.cache_data
def load_gis_data(file_path):

    with open(file_path, "r", encoding="utf-8") as file:
        geojson = json.load(file)

    records = []

    for feature in geojson["features"]:
        properties = feature.get(
            "properties", {}
        )

        records.append({
            "shapeID": properties.get("shapeID"),
            "District": properties.get("District"),
            "Division": properties.get("Division"),
            "priority_score": properties.get(
                "priority_score"
            ),
            "priority_level": properties.get(
                "priority_level"
            ),
            "verification_status": properties.get(
                "verification_status"
            ),
        })

    return geojson, pd.DataFrame(records)


if GIS_FILE.exists():

    geojson_data, gis_df = load_gis_data(
        str(GIS_FILE)
    )

    gis_df["priority_score"] = pd.to_numeric(
        gis_df["priority_score"],
        errors="coerce",
    )

    gis_df = gis_df.dropna(
        subset=["shapeID", "priority_score"]
    )

    st.metric(
        "Mapped DS Divisions",
        len(gis_df),
    )

    district_options_map = [
        "All Districts"
    ] + sorted(
        gis_df["District"].dropna().unique().tolist()
    )

    selected_map_district = st.selectbox(
        "Filter Map by District",
        district_options_map,
        key="gis_district_filter",
    )

    if selected_map_district == "All Districts":
        filtered_gis = gis_df.copy()

    else:
        filtered_gis = gis_df[
            gis_df["District"]
            == selected_map_district
        ].copy()

    if filtered_gis.empty:
        st.warning(
            "No mapped DS divisions for this selection."
        )

    else:

        # ====================================
        # MATCH SELECTED DS DIVISION
        # ====================================

        selected_map_record = gis_df[
            (
                gis_df["District"]
                .fillna("")
                .str.strip()
                .str.casefold()
                == district.strip().casefold()
            )
            &
            (
                gis_df["Division"]
                .fillna("")
                .str.strip()
                .str.casefold()
                == division.strip().casefold()
            )
        ]

        if not selected_map_record.empty:

            selected_map_row = (
                selected_map_record.iloc[0]
            )

            st.success(
                f"Selected analysis location: "
                f"{division}, {district}"
            )

            st.write(
                "Existing mapped flood scenario priority:",
                selected_map_row["priority_level"],
            )

            st.write(
                "Existing mapped flood scenario score:",
                round(
                    float(
                        selected_map_row["priority_score"]
                    ),
                    3,
                ),
            )

        else:
            st.info(
                "The selected DS division does not have "
                "an exact name match in this provisional "
                "GIS layer."
            )

        # ====================================
        # INTERACTIVE GIS CHOROPLETH
        # ====================================

        fig = px.choropleth_map(
            filtered_gis,
            geojson=geojson_data,
            locations="shapeID",
            featureidkey="properties.shapeID",
            color="priority_score",
            hover_name="Division",
            hover_data={
                "District": True,
                "priority_level": True,
                "priority_score": ":.3f",
                "shapeID": False,
            },
            color_continuous_scale="YlOrRd",
            range_color=(0, 1),
            map_style="carto-positron",
            zoom=7,
            center={
                "lat": 6.8,
                "lon": 80.3,
            },
            opacity=0.7,
            labels={
                "priority_score": "Priority Score",
            },
        )

        # ====================================
        # BLUE OUTLINE — STEP 36.2 FIX
        # ====================================

        if not selected_map_record.empty:

            selected_shape_id = str(
                selected_map_row["shapeID"]
            )

            selected_features = [
                feature
                for feature in geojson_data["features"]
                if str(
                    feature.get(
                        "properties", {}
                    ).get("shapeID")
                ) == selected_shape_id
            ]

            if selected_features:

                selected_geojson = {
                    "type": "FeatureCollection",
                    "features": selected_features,
                }

                fig.add_choroplethmap(
                    geojson=selected_geojson,
                    locations=[selected_shape_id],
                    z=[1],
                    featureidkey="properties.shapeID",
                    colorscale=[
                        [
                            0,
                            "rgba(0, 0, 255, 0.08)"
                        ],
                        [
                            1,
                            "rgba(0, 0, 255, 0.08)"
                        ],
                    ],
                    marker_opacity=1,
                    marker_line_color="#0047FF",
                    marker_line_width=5,
                    showscale=False,
                    showlegend=False,
                    hoverinfo="skip",
                    name="Selected DS Division",
                )

        fig.update_layout(
            height=650,
            margin=dict(
                r=0,
                t=0,
                l=0,
                b=0,
            ),
        )

        st.plotly_chart(
            fig,
            width="stretch",
        )

        # ====================================
        # GIS PRIORITY TABLE
        # ====================================

        st.subheader(
            "Mapped DS Division Priorities"
        )

        st.dataframe(
            filtered_gis[
                [
                    "District",
                    "Division",
                    "priority_score",
                    "priority_level",
                    "verification_status",
                ]
            ].sort_values(
                "priority_score",
                ascending=False,
            ),
            width="stretch",
        )

        st.caption(
            "Administrative-boundary matches are "
            "provisional. Some require verification. "
            "The displayed flood-priority values "
            "are simulated demonstration data."
        )

else:
    st.error(
        f"GIS file not found: {GIS_FILE}"
    )
