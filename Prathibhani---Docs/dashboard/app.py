
import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path

BASE = Path("/Users/ohaseelanka/disaster_analytics_hub")
DATA = BASE / "outputs/tables/flood_dashboard_demo.csv"

st.set_page_config(
    page_title="Human Impact Decision Support",
    page_icon="🌧️",
    layout="wide"
)

st.title("Multi-Hazard Human Impact Decision Support")
st.caption(
    "Research prototype | Simulated hazard inputs | "
    "Not an operational disaster warning system"
)

if not DATA.exists():
    st.error(f"Dataset not found: {DATA}")
    st.stop()

df = pd.read_csv(DATA)

st.sidebar.header("Filters")

districts = ["All"] + sorted(
    df["District"].dropna().unique().tolist()
)

selected_district = st.sidebar.selectbox(
    "Select District",
    districts
)

if selected_district != "All":
    df = df[df["District"] == selected_district].copy()

levels = ["Low", "Moderate", "High", "Very High"]

selected_levels = st.sidebar.multiselect(
    "Priority Levels",
    levels,
    default=levels
)

df = df[df["priority_level"].isin(selected_levels)].copy()

st.subheader("Flood Human-Impact Priority Overview")

c1, c2, c3, c4 = st.columns(4)

c1.metric("DS Divisions", len(df))
c2.metric("High Priority", (df["priority_level"] == "High").sum())
c3.metric(
    "Very High Priority",
    (df["priority_level"] == "Very High").sum()
)
c4.metric(
    "Average Priority Score",
    f"{df['priority_score'].mean():.3f}" if len(df) else "N/A"
)

left, right = st.columns(2)

with left:
    st.subheader("Priority Distribution")

    counts = (
        df["priority_level"]
        .value_counts()
        .reindex(levels, fill_value=0)
        .reset_index()
    )
    counts.columns = ["Priority Level", "DS Divisions"]

    fig = px.bar(
        counts,
        x="Priority Level",
        y="DS Divisions",
        color="Priority Level",
        color_discrete_map={
            "Low": "#22c55e",
            "Moderate": "#eab308",
            "High": "#f97316",
            "Very High": "#ef4444"
        }
    )
    st.plotly_chart(fig, use_container_width=True)

with right:
    st.subheader("Top Priority Divisions")

    top = df.nlargest(10, "priority_score")

    fig = px.bar(
        top,
        x="priority_score",
        y="Division",
        orientation="h",
        color="priority_level",
        color_discrete_map={
            "Low": "#22c55e",
            "Moderate": "#eab308",
            "High": "#f97316",
            "Very High": "#ef4444"
        }
    )
    fig.update_layout(yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig, use_container_width=True)

st.subheader("DS Division Priority Ranking")

st.dataframe(
    df[
        [
            "District",
            "Division",
            "priority_score",
            "priority_level",
            "main_risk_driver"
        ]
    ].sort_values("priority_score", ascending=False),
    use_container_width=True,
    hide_index=True
)

st.subheader("Explainable Priority Breakdown")

if not df.empty:
    division_options = (
        df["District"] + " — " + df["Division"]
    ).tolist()

    selected = st.selectbox(
        "Choose a DS Division",
        division_options
    )

    selected_row = df.loc[
        (df["District"] + " — " + df["Division"]) == selected
    ].iloc[0]

    contributions = pd.DataFrame({
        "Factor": [
            "Hazard",
            "Exposure",
            "Sensitivity"
        ],
        "Contribution": [
            selected_row["hazard_contribution"],
            selected_row["exposure_contribution"],
            selected_row["sensitivity_contribution"]
        ]
    })

    fig = px.bar(
        contributions,
        x="Factor",
        y="Contribution",
        color="Factor",
        title=f"Priority explanation: {selected}"
    )

    st.plotly_chart(fig, use_container_width=True)

    st.info(
        f"Main contributing factor: "
        f"{selected_row['main_risk_driver']}"
    )

st.warning(
    "All hazard severity values in this demonstration are simulated. "
    "Scores and priority categories are provisional and must not be "
    "used for real emergency decisions."
)

# ============================================================
# INTERACTIVE FLOOD DS-DIVISION MAP
# ============================================================

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

st.divider()
st.subheader("Flood Human-Impact Priority Map")

st.warning(
    "Research demonstration only. Hazard severity and priority "
    "scores are simulated. This is not an operational flood warning."
)

BASE_DIR = Path(__file__).resolve().parents[1]

MAP_PATH = (
    BASE_DIR / "outputs/gis/flood_ds_priority_map.geojson"
)

with MAP_PATH.open(encoding="utf-8") as f:
    map_geojson = json.load(f)

map_records = pd.DataFrame([
    feature["properties"]
    for feature in map_geojson["features"]
])

# Filter by district
district_options = ["All districts"] + sorted(
    map_records["District"].unique().tolist()
)

selected_map_district = st.selectbox(
    "Select district for map",
    district_options,
    key="flood_map_district"
)

if selected_map_district == "All districts":
    filtered_map = map_records.copy()
else:
    filtered_map = map_records[
        map_records["District"] == selected_map_district
    ].copy()

# Filter the polygons to the selected district
selected_shape_ids = set(filtered_map["shapeID"])

filtered_geojson = {
    "type": "FeatureCollection",
    "features": [
        feature
        for feature in map_geojson["features"]
        if feature["properties"]["shapeID"] in selected_shape_ids
    ]
}

# Set the display order for categories
risk_order = ["Low", "Moderate", "High", "Very High"]

risk_colors = {
    "Low": "#2ECC71",
    "Moderate": "#F1C40F",
    "High": "#E67E22",
    "Very High": "#E74C3C"
}

fig = px.choropleth_map(
    filtered_map,
    geojson=filtered_geojson,
    locations="shapeID",
    featureidkey="properties.shapeID",
    color="priority_level",
    category_orders={"priority_level": risk_order},
    color_discrete_map=risk_colors,
    hover_name="Division",
    hover_data={
        "District": True,
        "priority_score": ":.3f",
        "priority_level": True,
        "verification_status": True,
        "shapeID": False
    },
    map_style="carto-positron",
    center={"lat": 7.0, "lon": 80.5},
    zoom=7,
    opacity=0.7,
    labels={
        "priority_level": "Simulated priority",
        "priority_score": "Priority score",
        "verification_status": "Boundary check"
    }
)

fig.update_layout(
    height=650,
    margin=dict(l=0, r=0, t=0, b=0),
    legend_title_text="Simulated priority"
)

st.plotly_chart(
    fig,
    use_container_width=True
)

st.caption(
    f"Displaying {len(filtered_map)} mapped DS divisions. "
    "Eight polygons require further boundary review. "
    "Hanwella is not mapped pending administrative-name verification."
)

with st.expander("View geographic verification details"):
    st.dataframe(
        filtered_map[
            [
                "District",
                "Division",
                "priority_level",
                "priority_score",
                "verification_status",
                "district_overlap_ratio"
            ]
        ],
        use_container_width=True,
        hide_index=True
    )

    # ============================================================
# TRAINED HUMAN-IMPACT MODEL + SHAP EXPLANATIONS
# ============================================================

import sys
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.express as px

BASE_DIR = Path(__file__).resolve().parents[1]

if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.human_impact_predictor import HumanImpactPredictor


@st.cache_resource
def load_impact_predictor(hazard):
    return HumanImpactPredictor(hazard)


@st.cache_data
def load_impact_records(hazard):
    path = BASE_DIR / f"data/final/{hazard}_test.csv"
    return pd.read_csv(path)


st.divider()
st.header("ML Human-Impact Prediction and SHAP Explainability")

st.info(
    "Experimental machine-learning predictions based on historical "
    "records. These models are not validated for operational disaster warnings."
)

selected_hazard = st.selectbox(
    "Select hazard",
    ["flood", "landslide"],
    format_func=lambda x: x.capitalize(),
    key="ml_hazard_selector"
)

records = load_impact_records(selected_hazard)

record_options = records.index.tolist()

selected_record = st.selectbox(
    "Select historical test record",
    record_options,
    format_func=lambda i: (
        f"{records.loc[i, 'District']} | "
        f"{records.loc[i, 'Division']} | "
        f"{records.loc[i, 'Date']}"
    ),
    key="ml_record_selector"
)

selected_data = records.iloc[[selected_record]]

predictor = load_impact_predictor(selected_hazard)

result = predictor.predict(selected_data)

st.subheader("Predicted Human-Impact Category")

col1, col2 = st.columns(2)

with col1:
    st.metric(
        "Predicted impact",
        result["predicted_impact"]
    )

with col2:
    st.metric(
        "Predicted-class probability",
        f"{result['confidence'] * 100:.2f}%"
    )

# ------------------------------------------------------------
# CLASS PROBABILITIES
# ------------------------------------------------------------

probability_df = pd.DataFrame({
    "Impact category": list(
        result["class_probabilities"].keys()
    ),
    "Probability": list(
        result["class_probabilities"].values()
    )
})

fig_prob = px.bar(
    probability_df,
    x="Impact category",
    y="Probability",
    color="Impact category",
    title="Model Predicted Class Probabilities"
)

fig_prob.update_yaxes(range=[0, 1])

st.plotly_chart(
    fig_prob,
    use_container_width=True
)

# ------------------------------------------------------------
# SHAP EXPLANATIONS
# ------------------------------------------------------------

st.subheader("SHAP Feature Contributions")

shap_df = pd.DataFrame(
    result["shap_explanation"]
)

fig_shap = px.bar(
    shap_df.sort_values("shap_value"),
    x="shap_value",
    y="feature_name",
    orientation="h",
    color="shap_value",
    color_continuous_scale="RdBu",
    color_continuous_midpoint=0,
    title=(
        "SHAP Contributions to the "
        f"'{result['predicted_impact']}' Class Probability"
    )
)

fig_shap.update_layout(
    xaxis_title="SHAP contribution (probability units)",
    yaxis_title="Feature"
)

st.plotly_chart(
    fig_shap,
    use_container_width=True
)

st.caption(
    "Positive SHAP values increase the predicted probability "
    "of the selected impact category relative to the model's "
    "baseline. Negative values decrease it."
)

with st.expander("View SHAP values"):
    st.dataframe(
        shap_df[
            ["feature_name", "feature_value", "shap_value"]
        ],
        use_container_width=True,
        hide_index=True
    )

st.caption(
    "The selected records are from the historical test dataset. "
    "This interface demonstrates inference on previously recorded "
    "events, not forecasts of future disasters."
)