"""
Module 4 — Drift Tracker
Analyzes how quantities change over time for each attribute.
Computes drift velocity, stability score, anomalies, and plots timelines.
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from dataclasses import dataclass, field




@dataclass
class AttributeDrift:
    attribute: str
    timeline: pd.DataFrame          # columns: timestamp, quantity
    drift_velocity: float           # avg absolute change per month
    stability_score: float          # fraction of revisions where value changed
    anomalies: pd.DataFrame         # subset of timeline rows flagged as anomalies



def _build_timeline(df: pd.DataFrame) -> pd.DataFrame:
    """Sort by timestamp and reset index."""
    return df.sort_values("timestamp").reset_index(drop=True)


def _drift_velocity(timeline: pd.DataFrame) -> float:

    if len(timeline) < 2:
        return 0.0

    diffs = []
    for i in range(1, len(timeline)):
        delta_q = abs(timeline.loc[i, "quantity"] - timeline.loc[i - 1, "quantity"])
        delta_t = (timeline.loc[i, "timestamp"] - timeline.loc[i - 1, "timestamp"])
        months = delta_t.days / 30.44  # average days per month
        if months > 0:
            diffs.append(delta_q / months)

    return float(np.mean(diffs)) if diffs else 0.0


def _stability_score(timeline: pd.DataFrame) -> float:

    if len(timeline) < 2:
        return 0.0
    changed = (timeline["quantity"].diff().iloc[1:] != 0).sum()
    return float(changed / (len(timeline) - 1))


def _detect_anomalies(timeline: pd.DataFrame, window: int = 3, z_thresh: float = 2.0) -> pd.DataFrame:
   
    if len(timeline) < window + 1:
        return pd.DataFrame(columns=timeline.columns)

    tl = timeline.copy()
    tl["delta"] = tl["quantity"].diff().abs()

    # Rolling stats on the delta series
    tl["roll_mean"] = tl["delta"].rolling(window, min_periods=1).mean()
    tl["roll_std"]  = tl["delta"].rolling(window, min_periods=1).std().fillna(0)

    # Flag where delta > mean + z * std
    tl["anomaly"] = tl["delta"] > (tl["roll_mean"] + z_thresh * tl["roll_std"])

    anomalies = tl[tl["anomaly"]].copy()
    return anomalies[["timestamp", "quantity"]].reset_index(drop=True)


def analyze_attribute(records: list[tuple], attribute: str,
                      window: int = 3, z_thresh: float = 2.0) -> AttributeDrift:
    
    df = pd.DataFrame(records, columns=["timestamp", "attribute", "quantity"])
    df = df[df["attribute"] == attribute].copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["quantity"] = pd.to_numeric(df["quantity"])

    timeline = _build_timeline(df[["timestamp", "quantity"]])
    velocity = _drift_velocity(timeline)
    stability = _stability_score(timeline)
    anomalies = _detect_anomalies(timeline, window=window, z_thresh=z_thresh)

    return AttributeDrift(
        attribute=attribute,
        timeline=timeline,
        drift_velocity=velocity,
        stability_score=stability,
        anomalies=anomalies,
    )


def track_drift(records: list[tuple],
                window: int = 3,
                z_thresh: float = 2.0) -> dict[str, AttributeDrift]:
    """
    Main entry point. Analyzes all attributes present in records.

    Args:
        records:  list of (timestamp_str, attribute, quantity) tuples
        window:   rolling window for anomaly detection
        z_thresh: z-score threshold (default 2.0 → flag if > 2 std devs)

    Returns:
        dict mapping attribute name → AttributeDrift
    """
    df = pd.DataFrame(records, columns=["timestamp", "attribute", "quantity"])
    attributes = df["attribute"].unique()

    return {
        attr: analyze_attribute(records, attr, window=window, z_thresh=z_thresh)
        for attr in attributes
    }

#visualization

def plot_drift(drift: AttributeDrift, ax: plt.Axes | None = None,
               save_path: str | None = None) -> None:
    """
    Plot quantity vs time for one attribute, highlighting anomalies.
    """
    standalone = ax is None
    if standalone:
        fig, ax = plt.subplots(figsize=(10, 4))

    tl = drift.timeline
    ax.plot(tl["timestamp"], tl["quantity"],
            marker="o", linewidth=1.8, color="steelblue", label="Quantity")

    if not drift.anomalies.empty:
        ax.scatter(drift.anomalies["timestamp"], drift.anomalies["quantity"],
                   color="red", zorder=5, s=80, label="Anomaly")

    ax.set_title(
        f"{drift.attribute.title()}  |  "
        f"Drift velocity: {drift.drift_velocity:.4g}/mo  |  "
        f"Stability: {drift.stability_score:.0%}"
    )
    ax.set_xlabel("Date")
    ax.set_ylabel("Quantity")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right")
    ax.legend()
    ax.grid(True, linestyle="--", alpha=0.4)

    if standalone:
        plt.tight_layout()
        if save_path:
            plt.savefig(save_path, dpi=150)
            print(f"Saved plot → {save_path}")
        else:
            plt.show()


def plot_all(results: dict[str, AttributeDrift], save_path: str | None = None) -> None:
    """Plot all attributes in a grid."""
    n = len(results)
    cols = min(n, 2)
    rows = (n + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(11 * cols, 4 * rows))
    axes = np.array(axes).flatten()

    for ax, (attr, drift) in zip(axes, results.items()):
        plot_drift(drift, ax=ax)

    # Hide unused subplots
    for ax in axes[n:]:
        ax.set_visible(False)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path, dpi=150)
        print(f"Saved combined plot → {save_path}")
    else:
        plt.show()



def print_report(results: dict[str, AttributeDrift]) -> None:
    """Print a human-readable summary for all attributes."""
    for attr, drift in results.items():
        print(f"\n{'='*55}")
        print(f"Attribute      : {attr}")
        print(f"Revisions      : {len(drift.timeline)}")
        print(f"Drift Velocity : {drift.drift_velocity:.6g} units/month")
        print(f"Stability Score: {drift.stability_score:.2%}")
        print(f"Timeline:")
        for _, row in drift.timeline.iterrows():
            flag = " ← ANOMALY" if not drift.anomalies.empty and (
                drift.anomalies["timestamp"] == row["timestamp"]
            ).any() else ""
            print(f"  {str(row['timestamp'])[:10]}  {row['quantity']}{flag}")
        if not drift.anomalies.empty:
            print(f"Anomalies ({len(drift.anomalies)}):")
            for _, row in drift.anomalies.iterrows():
                print(f"  {str(row['timestamp'])[:10]}  {row['quantity']}")



