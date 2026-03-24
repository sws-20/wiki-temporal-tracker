"""
Visualizer — Wikipedia Quantity Drift Tracker
Interactive Streamlit dashboard.

Run with:
    streamlit run app.py
"""

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from drift_tracker import analyze_attribute

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Wikipedia Quantity Drift Tracker",
    page_icon="📈",
    layout="wide",
)

st.title("📈 Wikipedia Quantity Drift Tracker")
st.caption("Track how numerical quantities in Wikipedia articles change over time.")

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data
def load_data(file) -> pd.DataFrame:
    """Load and parse the uploaded CSV file."""
    df = pd.read_csv(file)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce")
    df["edit_count"] = pd.to_numeric(df["edit_count"], errors="coerce").fillna(0).astype(int)
    df["anomaly"] = df["anomaly"].astype(str).str.lower().isin(["true", "1", "yes"])
    return df.sort_values("timestamp").reset_index(drop=True)


# Sidebar — file upload
with st.sidebar:
    st.header("Data Source")
    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    st.markdown("---")
    st.markdown(
        "**Expected columns:**\n"
        "`timestamp`, `attribute`, `quantity`, `edit_count`, `anomaly`"
    )
    st.markdown("---")
    z_thresh = st.slider("Anomaly z-threshold", 1.0, 4.0, 2.0, 0.1,
                         help="Flag changes > N std deviations from rolling mean")
    roll_window = st.slider("Rolling window (revisions)", 2, 10, 3,
                            help="Window size for anomaly detection")

# ---------------------------------------------------------------------------
# Guard: no file yet → show sample data option
# ---------------------------------------------------------------------------

if uploaded is None:
    st.info("Upload a CSV file in the sidebar to get started, or load the sample data below.")
    if st.button("Load sample data"):
        # Build a small in-memory sample so the dashboard is immediately usable
        import io, textwrap
        sample_csv = textwrap.dedent("""\
            timestamp,attribute,quantity,edit_count,anomaly
            2010-01-01,population,1.21,12,False
            2012-05-10,population,1.24,8,False
            2015-08-15,population,1.29,15,False
            2019-03-20,population,1.35,20,False
            2020-01-01,population,1.20,45,True
            2022-06-01,population,1.38,18,False
            2010-03-01,gdp,1.66,10,False
            2013-06-01,gdp,1.86,9,False
            2016-09-01,gdp,2.26,14,False
            2019-12-01,gdp,2.87,22,False
            2021-06-01,gdp,3.17,19,False
            2022-01-01,gdp,0.50,60,True
            2010-01-01,area,3.29,3,False
            2014-01-01,area,3.29,2,False
            2018-01-01,area,3.29,1,False
            2022-01-01,area,3.29,2,False
        """)
        uploaded = io.StringIO(sample_csv)
    else:
        st.stop()

df = load_data(uploaded)
attributes = sorted(df["attribute"].unique().tolist())

with st.sidebar:
    st.header("Filters")
    selected_attr = st.selectbox("Select attribute", attributes)

    # Optional date range filter
    min_date = df["timestamp"].min().date()
    max_date = df["timestamp"].max().date()
    date_range = st.date_input("Date range", value=(min_date, max_date),
                               min_value=min_date, max_value=max_date)

# Apply filters
filtered = df[df["attribute"] == selected_attr].copy()
if len(date_range) == 2:
    filtered = filtered[
        (filtered["timestamp"].dt.date >= date_range[0]) &
        (filtered["timestamp"].dt.date <= date_range[1])
    ]

if filtered.empty:
    st.warning("No data for the selected attribute and date range.")
    st.stop()

# Compute drift metrics via drift_tracker

records = list(zip(
    filtered["timestamp"].dt.strftime("%Y-%m-%d"),
    filtered["attribute"],
    filtered["quantity"],
))
drift = analyze_attribute(records, selected_attr, window=roll_window, z_thresh=z_thresh)

# Metric cards

st.subheader(f"Metrics — {selected_attr.title()}")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Revisions", len(filtered))
c2.metric("Drift Velocity", f"{drift.drift_velocity:.4g} / mo")
c3.metric("Stability Score", f"{drift.stability_score:.0%}")
c4.metric("Anomalies detected", len(drift.anomalies))

st.markdown("---")

# Combined chart: quantity timeline + edit frequency

# Separate normal and anomaly points
normal = filtered[~filtered["anomaly"]]
anomalies = filtered[filtered["anomaly"]]

fig = make_subplots(
    rows=2, cols=1,
    shared_xaxes=True,
    row_heights=[0.65, 0.35],
    vertical_spacing=0.06,
    subplot_titles=(
        f"{selected_attr.title()} — Quantity over Time",
        "Edit Frequency",
    ),
)

# --- Row 1: quantity line ---
fig.add_trace(
    go.Scatter(
        x=normal["timestamp"], y=normal["quantity"],
        mode="lines+markers",
        name="Quantity",
        line=dict(color="steelblue", width=2),
        marker=dict(size=6),
        hovertemplate="%{x|%Y-%m-%d}<br>Quantity: %{y}<extra></extra>",
    ),
    row=1, col=1,
)

# Anomaly markers (red)
if not anomalies.empty:
    fig.add_trace(
        go.Scatter(
            x=anomalies["timestamp"], y=anomalies["quantity"],
            mode="markers",
            name="Anomaly",
            marker=dict(color="red", size=12, symbol="x", line=dict(width=2)),
            hovertemplate="%{x|%Y-%m-%d}<br>⚠ Anomaly: %{y}<extra></extra>",
        ),
        row=1, col=1,
    )

# Computed anomalies from drift_tracker (may differ from CSV flags)
if not drift.anomalies.empty:
    fig.add_trace(
        go.Scatter(
            x=drift.anomalies["timestamp"], y=drift.anomalies["quantity"],
            mode="markers",
            name="Computed anomaly",
            marker=dict(color="orange", size=10, symbol="circle-open", line=dict(width=2)),
            hovertemplate="%{x|%Y-%m-%d}<br>Computed anomaly: %{y}<extra></extra>",
        ),
        row=1, col=1,
    )

# --- Row 2: edit frequency bar ---
fig.add_trace(
    go.Bar(
        x=filtered["timestamp"], y=filtered["edit_count"],
        name="Edit count",
        marker_color="mediumseagreen",
        opacity=0.75,
        hovertemplate="%{x|%Y-%m-%d}<br>Edits: %{y}<extra></extra>",
    ),
    row=2, col=1,
)

fig.update_layout(
    height=620,
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    hovermode="x unified",
    margin=dict(t=60, b=40),
)
fig.update_yaxes(title_text="Quantity", row=1, col=1)
fig.update_yaxes(title_text="Edits", row=2, col=1)
fig.update_xaxes(title_text="Date", row=2, col=1)

st.plotly_chart(fig, use_container_width=True)

# Anomaly table

if not anomalies.empty or not drift.anomalies.empty:
    st.subheader("Flagged Anomalies")
    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("From uploaded data (`anomaly=True`)")
        if not anomalies.empty:
            st.dataframe(
                anomalies[["timestamp", "quantity", "edit_count"]].reset_index(drop=True),
                use_container_width=True,
            )
        else:
            st.write("None")

    with col_b:
        st.markdown("Computed by drift tracker (z-score method)")
        if not drift.anomalies.empty:
            st.dataframe(drift.anomalies.reset_index(drop=True), use_container_width=True)
        else:
            st.write("None")

# Raw data expander

with st.expander("Raw data"):
    st.dataframe(filtered.reset_index(drop=True), use_container_width=True)
