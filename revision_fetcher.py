#retrieving sample wikipedia revisions
import time
import json
from datetime import datetime, timezone
from dateutil.relativedelta import relativedelta
import requests
import pandas as pd

API_URL = "https://en.wikipedia.org/w/api.php"
DEFAULT_YEARS = 5
RATE_LIMIT_SLEEP = 1.0  # seconds between requests


def _month_windows(years: int) -> list[tuple[str, str]]:
    """Generate (start, end) ISO 8601 pairs for each month in the time window."""
    now = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    windows = []
    for i in range(years * 12):
        end = now - relativedelta(months=i)
        start = end - relativedelta(months=1)
        windows.append((start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ")))
    return windows


def _fetch_revision_for_window(title: str, start: str, end: str, session: requests.Session) -> dict | None:
    """Fetch the oldest revision within a given time window for an article."""
    params = {
        "action": "query",
        "titles": title,
        "prop": "revisions",
        "rvprop": "ids|timestamp|content",
        "rvslots": "main",
        "rvlimit": 1,
        "rvstart": end,    
        "rvend": start,
        "rvdir": "older",
        "format": "json",
        "formatversion": "2",
    }

    while True:
        response = session.get(API_URL, params=params, timeout=15)
        response.raise_for_status()
        data = response.json()

        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return None

        page = pages[0]
        if "missing" in page or "revisions" not in page:
            return None

        rev = page["revisions"][0]
        content = rev.get("slots", {}).get("main", {}).get("content", "")

        return {
            "revision_id": rev["revid"],
            "timestamp": rev["timestamp"],
            "content": content,
        }


def fetch_revisions(
    entity: str,
    years: int = DEFAULT_YEARS,
    rate_limit: float = RATE_LIMIT_SLEEP,
) -> pd.DataFrame:
    
    windows = _month_windows(years)
    revisions = []

    with requests.Session() as session:
        session.headers.update({"User-Agent": "RevisionFetcher/1.0 (research tool)"})

        for start, end in windows:
            print(f"Fetching revision for {entity} | window {start[:7]}")
            rev = _fetch_revision_for_window(entity, start, end, session)
            if rev:
                revisions.append(rev)
            time.sleep(rate_limit)

    df = pd.DataFrame(revisions, columns=["revision_id", "timestamp", "content"])
    df.drop_duplicates(subset="revision_id", inplace=True)
    df.sort_values("timestamp", inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


def save_revisions(df: pd.DataFrame, path: str) -> None:
    """Save revisions DataFrame to a JSON file."""
    records = df.to_dict(orient="records")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"Saved {len(records)} revisions to {path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch sampled Wikipedia revisions.")
    parser.add_argument("entity", help='Wikipedia article title, e.g. "Elon Musk"')
    parser.add_argument("--years", type=int, default=DEFAULT_YEARS, help="Years to look back (default: 5)")
    parser.add_argument("--output", default="revisions.json", help="Output JSON file path")
    parser.add_argument("--rate-limit", type=float, default=RATE_LIMIT_SLEEP, help="Sleep between requests (seconds)")
    args = parser.parse_args()

    df = fetch_revisions(args.entity, years=args.years, rate_limit=args.rate_limit)
    print(df[["revision_id", "timestamp"]].to_string())
    save_revisions(df, args.output)
