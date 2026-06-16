import pandas as pd
import sqlite3

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────
DATASET_PATH = "exception_dataset_100000.csv"
DB_PATH      = "exceptions.db"


def get_historical_data(description):
    """
    Query BOTH the synthetic CSV dataset and the live SQLite database
    for past exceptions whose description shares the first 15 characters
    with the submitted description.

    Returns a combined result dict, or None if no matches are found
    in either source.
    """

    prefix = description[:15]

    # ── 1. Load from CSV ──────────────────────────────────────
    try:
        csv_df = pd.read_csv(DATASET_PATH, usecols=[
            "Description", "Status", "Duration_Days", "Created_Date"
        ])
        csv_matches = csv_df[
            csv_df["Description"].str.contains(prefix, case=False, na=False)
        ].copy()
        csv_matches = csv_matches.rename(columns={
            "Description":  "description",
            "Status":       "status",
            "Duration_Days":"duration_days",
            "Created_Date": "created_date",
        })
    except Exception:
        csv_matches = pd.DataFrame(
            columns=["description", "status", "duration_days", "created_date"]
        )

    # ── 2. Load from live SQLite DB ───────────────────────────
    try:
        conn = sqlite3.connect(DB_PATH)
        db_df = pd.read_sql_query(
            """
            SELECT description, status, duration_days, created_date
            FROM   exceptions
            WHERE  status IN ('Approved', 'Rejected', 'Expired', 'Under Review')
            """,
            conn,
        )
        conn.close()
        db_matches = db_df[
            db_df["description"].str.contains(prefix, case=False, na=False)
        ].copy()
    except Exception:
        db_matches = pd.DataFrame(
            columns=["description", "status", "duration_days", "created_date"]
        )

    # ── 3. Combine both sources ───────────────────────────────
    combined = pd.concat([csv_matches, db_matches], ignore_index=True)

    if combined.empty:
        return None

    # ── 4. Compute statistics ─────────────────────────────────
    total    = len(combined)
    approved = int((combined["status"] == "Approved").sum())
    rejected = int((combined["status"] == "Rejected").sum())

    avg_duration  = round(combined["duration_days"].dropna().mean(), 2)
    approval_rate = round((approved / total) * 100, 2)

    # ── 5. Confidence level ───────────────────────────────────
    if approval_rate >= 80:
        confidence = "High"
    elif approval_rate >= 60:
        confidence = "Medium"
    else:
        confidence = "Low"

    # ── 6. Source breakdown (informational) ───────────────────
    csv_count = len(csv_matches)
    db_count  = len(db_matches)

    return {
        "count":                total,
        "approved":             approved,
        "rejected":             rejected,
        "avg_duration":         avg_duration,
        "approval_rate":        approval_rate,
        "confidence":           confidence,
        "recommended_duration": min(round(avg_duration), 30),
        "last_date":            combined["created_date"].max(),
        "csv_matches":          csv_count,
        "db_matches":           db_count,
    }
