import sqlite3

# ==================================================
# DATABASE CONFIGURATION
# ==================================================

DB_PATH = "exceptions.db"


def get_db():
    """Return a connection with row_factory enabled."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """
    Create all required tables if they do not exist,
    and apply any pending schema migrations.
    Full schema matches the CSV training dataset columns plus
    approval workflow and ML retraining fields.
    """
    conn = get_db()
    cur  = conn.cursor()

    # --------------------------------------------------
    # EXCEPTIONS TABLE  — full schema
    # --------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exceptions (
            id                INTEGER   PRIMARY KEY AUTOINCREMENT,

            -- Identification
            exception_id      TEXT      UNIQUE NOT NULL,

            -- Core description
            description       TEXT      NOT NULL,
            category          TEXT,

            -- Organisation / asset (matches CSV columns)
            business_unit     TEXT,
            asset_name        TEXT,

            -- Risk factors (matches CSV columns)
            asset_criticality TEXT,
            business_impact   TEXT,
            compliance_impact TEXT,
            threat_exposure   TEXT,

            -- Duration & scoring (matches CSV columns)
            duration_days     INTEGER,
            risk_score        INTEGER,
            risk_level        TEXT,
            recommendation    TEXT,

            -- Workflow status
            status            TEXT      DEFAULT 'Pending',

            -- People (matches CSV columns)
            requested_by      TEXT,
            risk_owner        TEXT,

            -- Dates (matches CSV columns)
            created_date      TEXT,
            expiry_date       TEXT,

            -- Approval details
            approved_date     TEXT,
            approved_datetime TEXT,
            approved_by       TEXT,
            approver_id       TEXT,
            approver_title    TEXT,

            -- Rejection
            rejection_reason  TEXT,

            -- ML retraining flag
            ml_retrained      INTEGER   DEFAULT 0,

            -- Audit timestamp
            created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # --------------------------------------------------
    # ML RETRAIN LOG TABLE
    # --------------------------------------------------
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ml_retrain_log (
            id           INTEGER   PRIMARY KEY AUTOINCREMENT,
            retrained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            records_used INTEGER,
            accuracy     REAL,
            notes        TEXT
        )
    """)

    conn.commit()

    # --------------------------------------------------
    # SCHEMA MIGRATIONS
    # Apply ALTER TABLE for any column added after the
    # initial release so existing databases are upgraded
    # automatically without data loss.
    # --------------------------------------------------
    migrations = [
        ("approved_datetime", "TEXT"),
        ("approver_id",       "TEXT"),
        ("approver_title",    "TEXT"),
    ]

    for col_name, col_type in migrations:
        try:
            cur.execute(
                f"ALTER TABLE exceptions ADD COLUMN {col_name} {col_type}"
            )
            conn.commit()
            print(f"[DB Migration] Added column: {col_name}")
        except sqlite3.OperationalError:
            pass  # Column already exists — safe to ignore

    conn.close()


# ==================================================
# RUN STANDALONE — initialise / migrate DB
# ==================================================

if __name__ == "__main__":
    init_db()

    conn = get_db()
    cur  = conn.cursor()

    cur.execute("PRAGMA table_info(exceptions)")
    cols = cur.fetchall()
    print("\n✅ Database initialised successfully.")
    print(f"   Path    : {DB_PATH}")
    print(f"   Table   : exceptions  ({len(cols)} columns)\n")
    print(f"   {'#':<4} {'Column':<25} {'Type'}")
    print(f"   {'-'*4} {'-'*25} {'-'*15}")
    for c in cols:
        print(f"   {c[0]:<4} {c[1]:<25} {c[2]}")

    cur.execute("SELECT COUNT(*) FROM exceptions")
    total = cur.fetchone()[0]
    print(f"\n   Total records in exceptions table: {total}")

    cur.execute("PRAGMA table_info(ml_retrain_log)")
    log_cols = cur.fetchall()
    print(f"\n   Table   : ml_retrain_log  ({len(log_cols)} columns)")

    conn.close()
