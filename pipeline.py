"""
pipeline.py — Full Pipeline Runner
Fetches Wikipedia revisions, extracts quantities, links attributes,
tracks drift, and saves a CSV ready to upload to app.py (Streamlit dashboard).

Usage:
    python pipeline.py "India" --years 5 --output india.csv
    python pipeline.py "Elon Musk" --years 3 --output elon.csv
"""

import argparse
import re
import pandas as pd
from datetime import timezone
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

# --- Import your modules (must be in the same folder) ---
from revision_fetcher import fetch_revisions
from quantity_extractor import extract_quantities
from attribute_linker import link_quantities
from drift_tracker import track_drift


# ---------------------------------------------------------------------------
# Wikitext cleaner
# ---------------------------------------------------------------------------

def clean_wikitext(text: str) -> str:
    """
    Strip basic wikitext markup so spaCy gets clean plain text.
    Removes: templates {{...}}, file/image links, HTML tags,
             wiki links [[...]], bold/italic markers.
    """
    # Remove templates like {{Infobox ...}} — handles nested braces
    while '{{' in text:
        text = re.sub(r'\{\{[^{}]*\}\}', '', text)

    # Remove file/image links [[File:...]] [[Image:...]]
    text = re.sub(r'\[\[(?:File|Image):[^\]]*\]\]', '', text, flags=re.IGNORECASE)

    # Convert wiki links [[target|label]] → label, [[target]] → target
    text = re.sub(r'\[\[(?:[^|\]]*\|)?([^\]]+)\]\]', r'\1', text)

    # Remove HTML tags
    text = re.sub(r'<[^>]+>', '', text)

    # Remove bold/italic wiki markers
    text = re.sub(r"'{2,}", '', text)

    # Remove section headers == Heading ==
    text = re.sub(r'={2,}[^=]+=+', '', text)

    # Remove references <ref>...</ref>
    text = re.sub(r'<ref[^>]*>.*?</ref>', '', text, flags=re.DOTALL)

    # Collapse extra whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text


# ---------------------------------------------------------------------------
# Glue: revision → list of (timestamp, attribute, quantity, edit_count) rows
# ---------------------------------------------------------------------------

def process_revision(timestamp: str, wikitext: str) -> list[dict]:
    """
    Run modules 2 and 3 on a single revision's wikitext.
    Returns a list of row dicts ready for the DataFrame.
    """
    rows = []
    plain_text = clean_wikitext(wikitext)

    # Module 2: extract quantities with their sentences
    quantities = extract_quantities(plain_text)

    for qty in quantities:
        sentence = qty.get("sentence", "")
        if not sentence:
            continue

        # Module 3: link each quantity's sentence to an attribute
        links = link_quantities(sentence)

        for link in links:
            # Match the link back to this quantity by checking if the
            # quantity text appears in the linked quantity text
            if qty["original_text"] in link["quantity"] or link["quantity"] in qty["original_text"]:
                rows.append({
                    "timestamp": timestamp,
                    "attribute": link["attribute"],
                    "quantity": qty["value"],
                    "unit": qty["unit"],
                    "original_text": qty["original_text"],
                    "edit_count": 0,   # filled in later
                    "anomaly": False,  # filled in by drift tracker
                })
                break

    return rows


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def run_pipeline(entity: str, years: int, output_path: str) -> pd.DataFrame:
    """
    Full pipeline:
      1. Fetch revisions from Wikipedia
      2. Extract + link quantities from each revision
      3. Track drift and flag anomalies
      4. Save CSV for the Streamlit dashboard
    """

    # ── Step 1: Fetch revisions ──────────────────────────────────────────
    print(f"\n[1/4] Fetching revisions for '{entity}' ({years} years)...")
    revisions_df = fetch_revisions(entity, years=years)
    print(f"      Got {len(revisions_df)} revisions.")

    if revisions_df.empty:
        print("No revisions found. Check the entity name.")
        return pd.DataFrame()

    # Count edits per month window (proxy: how many revisions exist that month)
    revisions_df["month"] = pd.to_datetime(revisions_df["timestamp"]).dt.to_period("M")
    edit_counts = revisions_df.groupby("month").size().to_dict()

    # ── Step 2: Extract & link quantities ───────────────────────────────
    print("\n[2/4] Extracting and linking quantities...")
    all_rows = []

    for _, rev in revisions_df.iterrows():
        timestamp = rev["timestamp"]
        wikitext = rev["content"]
        month_key = pd.to_datetime(timestamp).to_period("M")

        rows = process_revision(timestamp, wikitext)

        # Attach edit count for this month
        for row in rows:
            row["edit_count"] = edit_counts.get(month_key, 1)

        all_rows.extend(rows)
        print(f"      {timestamp[:10]} → {len(rows)} quantities found")

    if not all_rows:
        print("No quantities extracted. The article may need a different entity name.")
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)
    print(f"\n      Total rows extracted: {len(df)}")
    print(f"      Attributes found: {sorted(df['attribute'].unique())}")

    # ── Step 3: Drift tracking + anomaly detection ───────────────────────
    print("\n[3/4] Running drift tracker...")

    # Build records list for drift tracker: (timestamp, attribute, quantity)
    records = list(zip(df["timestamp"], df["attribute"], df["quantity"]))
    drift_results = track_drift(records, window=3, z_thresh=2.0)

    # Mark anomalies back onto the main DataFrame
    df["anomaly"] = False
    for attr, drift in drift_results.items():
        if drift.anomalies.empty:
            continue
        anomaly_timestamps = set(drift.anomalies["timestamp"].astype(str).str[:10])
        mask = (df["attribute"] == attr) & (df["timestamp"].str[:10].isin(anomaly_timestamps))
        df.loc[mask, "anomaly"] = True

    # ── Step 4: Save CSV ─────────────────────────────────────────────────
    print(f"\n[4/4] Saving CSV to '{output_path}'...")

    # Keep only the columns the Streamlit app needs
    output_df = df[["timestamp", "attribute", "quantity", "edit_count", "anomaly"]].copy()
    output_df.sort_values(["attribute", "timestamp"], inplace=True)
    output_df.reset_index(drop=True, inplace=True)
    output_df.to_csv(output_path, index=False)

    print(f"      Saved {len(output_df)} rows.")
    print(f"\nDone! Upload '{output_path}' to the Streamlit dashboard.")
    print(f"Run the dashboard with:  streamlit run app.py")

    return output_df


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wikipedia Quantity Drift Pipeline")
    parser.add_argument("entity", help='Wikipedia article title e.g. "India"')
    parser.add_argument("--years", type=int, default=5, help="Years to look back (default: 5)")
    parser.add_argument("--output", default="output.csv", help="Output CSV filename (default: output.csv)")
    args = parser.parse_args()

    df = run_pipeline(args.entity, years=args.years, output_path=args.output)

    if not df.empty:
        print("\nPreview:")
        print(df.head(10).to_string(index=False))