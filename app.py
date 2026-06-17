import streamlit as st
import pandas as pd
import joblib
import plotly.express as px
import plotly.graph_objects as go
import sqlite3
import os
from datetime import datetime, timedelta

from risk_engine import calculate_risk
from historical_engine import get_historical_data
from pdf_generator import create_report

# ─────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────
DB_PATH      = "exceptions.db"
MODEL_PATH   = "models/model.pkl"
DATASET_PATH = "exception_dataset_100000.csv"

RISK_COLORS = {
    "Critical": "#e53e3e",
    "High":     "#dd6b20",
    "Medium":   "#d69e2e",
    "Low":      "#38a169",
}

CHART_LAYOUT = dict(
    paper_bgcolor="white", plot_bgcolor="white",
    font=dict(family="Inter, sans-serif", size=12, color="#1a202c"),
    margin=dict(t=48, b=36, l=36, r=16),
    legend=dict(bgcolor="rgba(0,0,0,0)", bordercolor="rgba(0,0,0,0)"),
)

BUSINESS_UNITS = [
    "IT","Security","Finance","HR","Operations","Legal","Procurement",
    "Projects","Cloud","SOC","DevOps","Audit","Compliance","Research",
    "Infrastructure","Network","Application","Data Management",
    "Business Continuity","Administration",
]
ASSET_NAMES = [
    "ERP Server","Finance Server","HR Server","Active Directory","Database Server",
    "Cloud Portal","AWS Account","Azure Subscription","Firewall","VPN Gateway",
    "SIEM Platform","Email Gateway","Web Application","API Gateway",
    "Kubernetes Cluster","DevOps Pipeline","PKI Infrastructure","DLP Server",
    "Core Router","Analytics Platform",
]

# ─────────────────────────────────────────────────────────────
# DATABASE HELPERS
# ─────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db(); cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS exceptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            exception_id TEXT UNIQUE NOT NULL,
            description TEXT NOT NULL,
            category TEXT, business_unit TEXT, asset_name TEXT,
            asset_criticality TEXT, business_impact TEXT,
            compliance_impact TEXT, threat_exposure TEXT,
            duration_days INTEGER, risk_score INTEGER,
            risk_level TEXT, recommendation TEXT,
            status TEXT DEFAULT 'Pending',
            requested_by TEXT, risk_owner TEXT,
            created_date TEXT, expiry_date TEXT,
            approved_date TEXT, approved_datetime TEXT,
            approved_by TEXT, approver_id TEXT, approver_title TEXT,
            rejection_reason TEXT,
            ml_retrained INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ml_retrain_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            retrained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            records_used INTEGER, accuracy REAL, notes TEXT
        )""")
    conn.commit()
    for col, typ in [("approved_datetime","TEXT"),("approver_id","TEXT"),("approver_title","TEXT")]:
        try:
            cur.execute(f"ALTER TABLE exceptions ADD COLUMN {col} {typ}")
            conn.commit()
        except Exception:
            pass
    conn.close()

def save_exception(data):
    conn = get_db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM exceptions")
    exc_id = f"EX{cur.fetchone()[0]+1:06d}"
    created = datetime.today().strftime("%Y-%m-%d")
    expiry  = (datetime.today()+timedelta(days=data.get("recommended_duration",30))).strftime("%Y-%m-%d")
    cur.execute("""
        INSERT INTO exceptions (
            exception_id,description,category,business_unit,asset_name,
            asset_criticality,business_impact,compliance_impact,threat_exposure,
            duration_days,risk_score,risk_level,recommendation,status,
            requested_by,risk_owner,created_date,expiry_date
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'Pending',?,?,?,?)""",
        (exc_id, data["description"], data["category"], data["business_unit"],
         data["asset_name"], data["asset_criticality"], data["business_impact"],
         data["compliance_impact"], data["threat_exposure"], data["duration"],
         data["score"], data["risk"], data["recommendation"],
         data["requested_by"], data["risk_owner"], created, expiry))
    conn.commit(); conn.close()
    return exc_id

def update_status(exc_id, status, approved_by="", approver_id="",
                  approver_title="", rejection_reason=""):
    conn = get_db(); cur = conn.cursor()
    ad   = datetime.today().strftime("%Y-%m-%d")           if status=="Approved" else None
    adt  = datetime.now().strftime("%Y-%m-%d %H:%M:%S")   if status=="Approved" else None
    cur.execute("""
        UPDATE exceptions SET status=?,approved_date=?,approved_datetime=?,
        approved_by=?,approver_id=?,approver_title=?,rejection_reason=?
        WHERE exception_id=?""",
        (status,ad,adt,approved_by,approver_id,approver_title,rejection_reason,exc_id))
    conn.commit(); conn.close()

def get_pending():
    conn=get_db()
    df=pd.read_sql_query("SELECT * FROM exceptions WHERE status IN ('Pending','Under Review') ORDER BY created_at DESC",conn)
    conn.close(); return df

def get_all():
    conn=get_db()
    df=pd.read_sql_query("SELECT * FROM exceptions ORDER BY created_at DESC",conn)
    conn.close(); return df

def get_approved_for_ml():
    conn=get_db()
    df=pd.read_sql_query("SELECT * FROM exceptions WHERE status='Approved' AND ml_retrained=0",conn)
    conn.close(); return df

def mark_retrained(ids):
    if not ids: return
    conn=get_db(); cur=conn.cursor()
    cur.execute(f"UPDATE exceptions SET ml_retrained=1 WHERE id IN ({','.join(['?']*len(ids))})",ids)
    conn.commit(); conn.close()

def log_retrain(n,acc,notes=""):
    conn=get_db()
    conn.execute("INSERT INTO ml_retrain_log (records_used,accuracy,notes) VALUES (?,?,?)",(n,acc,notes))
    conn.commit(); conn.close()

def attempt_retrain():
    new_data=get_approved_for_ml()
    if len(new_data)<50:
        return False,f"Need 50 approved records ({len(new_data)} available)."
    try:
        from sklearn.pipeline import Pipeline
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.linear_model import LogisticRegression
        from sklearn.model_selection import train_test_split
        from sklearn.metrics import accuracy_score
        csv_df=pd.read_csv(DATASET_PATH,usecols=["Description","Category"])
        combined=pd.concat([
            csv_df.rename(columns={"Description":"description","Category":"category"}),
            new_data[["description","category"]]
        ],ignore_index=True).dropna()
        X_tr,X_te,y_tr,y_te=train_test_split(combined["description"],combined["category"],test_size=0.2,random_state=42)
        pipe=Pipeline([("tfidf",TfidfVectorizer(max_features=10000,ngram_range=(1,2))),
                       ("clf",LogisticRegression(max_iter=300,C=1.0))])
        pipe.fit(X_tr,y_tr)
        acc=accuracy_score(y_te,pipe.predict(X_te))
        os.makedirs("models",exist_ok=True)
        joblib.dump(pipe,MODEL_PATH)
        
        # Append new approved exceptions to the CSV dataset file
        column_mapping = {
            "exception_id": "Exception_ID",
            "description": "Description",
            "category": "Category",
            "business_unit": "Business_Unit",
            "asset_name": "Asset_Name",
            "asset_criticality": "Asset_Criticality",
            "business_impact": "Business_Impact",
            "compliance_impact": "Compliance_Impact",
            "threat_exposure": "Threat_Exposure",
            "requested_by": "Requested_By",
            "risk_owner": "Risk_Owner",
            "duration_days": "Duration_Days",
            "risk_score": "Risk_Score",
            "risk_level": "Risk_Level",
            "recommendation": "Recommendation",
            "status": "Status",
            "created_date": "Created_Date",
            "expiry_date": "Expiry_Date"
        }
        full_csv = pd.read_csv(DATASET_PATH)
        append_df = new_data[list(column_mapping.keys())].rename(columns=column_mapping)
        updated_csv = pd.concat([full_csv, append_df], ignore_index=True)
        updated_csv.to_csv(DATASET_PATH, index=False)
        
        mark_retrained(list(new_data["id"]))
        log_retrain(len(new_data),round(acc,4),f"Auto-retrain {datetime.today().strftime('%Y-%m-%d')}")
        return True,f"Retrained on {len(new_data)} records and appended to CSV. Accuracy: {acc:.2%}"
    except Exception as e:
        return False,f"Retraining failed: {e}"

def risk_rec(risk):
    return {"Critical":"Immediate Review Required","High":"Approve With Compensating Controls",
            "Medium":"Management Approval Required","Low":"Standard Approval"}.get(risk,"Standard Approval")

def rc(risk): return RISK_COLORS.get(risk,"#718096")

# ─────────────────────────────────────────────────────────────
# PAGE SETUP
# ─────────────────────────────────────────────────────────────
st.set_page_config(page_title="AI Exception Management",page_icon="🛡️",layout="wide")
init_db()

st.markdown("""<style>
.main{background-color:var(--background-color)}
section[data-testid="stSidebar"]{background:linear-gradient(180deg,#1a1f36 0%,#2d3561 100%)}
section[data-testid="stSidebar"] *{color:#e0e6ff!important}
section[data-testid="stSidebar"] .stButton>button{
  background:rgba(255,255,255,0.08);color:#e0e6ff!important;
  border:1px solid rgba(255,255,255,0.15);border-radius:8px;
  font-weight:500;margin-bottom:6px;transition:all 0.2s}
section[data-testid="stSidebar"] .stButton>button:hover{
  background:rgba(255,255,255,0.18);border-color:rgba(255,255,255,0.4)}

/* Ensure typed text is fully visible in both light & dark mode */
input, textarea {
  color: var(--text-color) !important;
}

/* KPI cards (Theme Aware: adapts to light/dark) */
.kpi-card{background:var(--secondary-background-color);border-radius:10px;padding:14px 16px;
  box-shadow:0 4px 12px rgba(0,0,0,0.08);border-left:4px solid #4f8ef7;margin-bottom:4px}
.kpi-card.critical{border-left-color:#e53e3e}
.kpi-card.high    {border-left-color:#dd6b20}
.kpi-card.medium  {border-left-color:#d69e2e}
.kpi-card.approved{border-left-color:#38a169}
.kpi-card.purple  {border-left-color:#805ad5}
.kpi-label{font-size:10px;color:var(--text-color);opacity:0.75;font-weight:700;text-transform:uppercase;
  letter-spacing:0.6px;margin-bottom:2px}
.kpi-value{font-size:26px;font-weight:700;color:var(--text-color);line-height:1.1}
.kpi-sub  {font-size:10px;color:var(--text-color);opacity:0.55;margin-top:2px}

/* KRI cards (Theme Aware) */
.kri-card{background:var(--secondary-background-color);border-radius:10px;padding:14px 16px;
  box-shadow:0 4px 12px rgba(0,0,0,0.08);border-left:4px solid #805ad5;margin-bottom:4px}
.kri-label{font-size:10px;color:#805ad5;font-weight:700;text-transform:uppercase;
  letter-spacing:0.6px;margin-bottom:2px}
.kri-value{font-size:26px;font-weight:700;color:var(--text-color);line-height:1.1}
.kri-sub  {font-size:10px;color:var(--text-color);opacity:0.55;margin-top:2px}

.section-bar{font-size:15px;font-weight:700;color:var(--text-color);
  margin:18px 0 10px;padding-bottom:5px;border-bottom:2px solid var(--secondary-background-color)}
.info-box{background:rgba(49,130,206,0.1);border-left:4px solid #3182ce;border-radius:8px;
  padding:11px 15px;margin:8px 0;font-size:13px;color:var(--text-color)}

/* PDF download highlight */
.pdf-ready{background:rgba(56,161,105,0.1);border:1.5px solid #38a169;border-radius:10px;
  padding:16px 20px;margin-top:12px;text-align:center}
</style>""", unsafe_allow_html=True)

st.markdown("<h1 style='margin-bottom:0'>🛡️ AI-Driven Exception Management & Risk Assessment</h1>",unsafe_allow_html=True)
st.markdown("<p style='color:#718096;margin-top:4px;margin-bottom:20px;font-size:14px'>"
            "Intelligent risk classification · Automated DB persistence · Continuous ML retraining</p>",
            unsafe_allow_html=True)

try:
    model = joblib.load(MODEL_PATH)
except Exception:
    model = None

# ─────────────────────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────────────────────
if "menu" not in st.session_state:
    st.session_state["menu"] = "Dashboard"

st.sidebar.markdown(
    "<div style='text-align:center;padding:14px 0 6px'>"
    "<span style='font-size:30px'>🛡️</span><br>"
    "<span style='font-size:13px;font-weight:600;letter-spacing:1px;opacity:0.7'>EXCEPTION MANAGER</span>"
    "</div>", unsafe_allow_html=True)
st.sidebar.markdown("---")
st.sidebar.markdown("<p style='font-size:10px;letter-spacing:1.5px;opacity:0.5;margin-bottom:6px'>NAVIGATION</p>",
                    unsafe_allow_html=True)

for icon,label in [("📊","Dashboard"),("📝","Submit Exception"),
                   ("🔍","Search Exception"),("🔬","Analyse & Approve"),("🤖","ML Retraining")]:
    if st.sidebar.button(f"{icon}  {label}", use_container_width=True, key=f"nav_{label}"):
        st.session_state["menu"] = label
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown(f"<p style='font-size:11px;opacity:0.55;text-align:center'>"
                    f"Active: <b>{st.session_state['menu']}</b></p>", unsafe_allow_html=True)
conn_s = get_db()
tot_s  = pd.read_sql_query("SELECT COUNT(*) as n FROM exceptions",conn_s).iloc[0,0]
pend_s = pd.read_sql_query("SELECT COUNT(*) as n FROM exceptions WHERE status='Pending'",conn_s).iloc[0,0]
conn_s.close()
st.sidebar.markdown(f"<div style='text-align:center;font-size:11px;opacity:0.65;margin-top:6px'>"
                    f"DB Records: <b>{tot_s}</b> | Pending: <b>{pend_s}</b></div>",
                    unsafe_allow_html=True)

menu = st.session_state["menu"]

# ═════════════════════════════════════════════════════════════
# SUBMIT EXCEPTION
# ═════════════════════════════════════════════════════════════
if menu == "Submit Exception":
    st.markdown("<div class='section-bar'>📝 Submit New Exception</div>", unsafe_allow_html=True)
    st.markdown("<div class='info-box'>Submitted exceptions are saved with status <b>Pending</b>. "
                "Go to <b>🔬 Analyse & Approve</b> to run AI analysis and decide.</div>",
                unsafe_allow_html=True)

    description = st.text_area("Exception Description *",
                               placeholder="Describe the exception clearly...", height=110)
    st.markdown("##### Requester Details")
    r1,r2 = st.columns(2)
    with r1: requested_by = st.text_input("Requested By *", placeholder="EMP_1234 or John Smith")
    with r2: risk_owner   = st.text_input("Risk Owner",     placeholder="MGR_567 or Jane Doe")

    st.markdown("##### Classification")
    c1,c2 = st.columns(2)
    with c1: business_unit = st.selectbox("Business Unit *", BUSINESS_UNITS)
    with c2: asset_name    = st.selectbox("Asset Name *",    ASSET_NAMES)

    st.markdown("##### Risk Factors")
    f1,f2,f3 = st.columns(3)
    with f1: asset_criticality = st.selectbox("Asset Criticality *", ["Low","Medium","High"])
    with f2: business_impact   = st.selectbox("Business Impact *",   ["Low","Medium","High"])
    with f3: duration          = st.number_input("Duration (Days) *", 1, 365, value=30)
    f4,f5 = st.columns(2)
    with f4: compliance_impact = st.selectbox("Compliance Impact *", ["Low","Medium","High"])
    with f5: threat_exposure   = st.selectbox("Threat Exposure *",   ["Low","Medium","High"])

    if st.button("💾 Submit Exception", type="primary"):
        if not description.strip():
            st.error("Please enter an exception description.")
        elif not requested_by.strip():
            st.error("Please enter the requester name or ID.")
        else:
            with st.spinner("Saving..."):
                score, risk    = calculate_risk(asset_criticality, business_impact, duration,
                                               compliance_impact, threat_exposure)
                recommendation = risk_rec(risk)
                category       = model.predict([description])[0] if model else "Unknown"
            exc_id = save_exception({
                "description":description,"category":category,
                "business_unit":business_unit,"asset_name":asset_name,
                "asset_criticality":asset_criticality,"business_impact":business_impact,
                "compliance_impact":compliance_impact,"threat_exposure":threat_exposure,
                "duration":duration,"score":score,"risk":risk,"recommendation":recommendation,
                "requested_by":requested_by,"risk_owner":risk_owner,
                "recommended_duration":duration,
            })
            color = rc(risk)
            st.success(f"✅ Exception **{exc_id}** saved. Go to **🔬 Analyse & Approve** to continue.")
            m1,m2,m3 = st.columns(3)
            for col,lbl,val,c in [(m1,"Exception ID",exc_id,"#4f8ef7"),
                                   (m2,"Category",category,"#4f8ef7"),
                                   (m3,"Risk Level",f"{risk} ({score})",color)]:
                with col:
                    st.markdown(f"<div class='kpi-card' style='border-left-color:{c}'>"
                                f"<div class='kpi-label'>{lbl}</div>"
                                f"<div class='kpi-value' style='font-size:18px;color:{c}'>{val}</div>"
                                f"</div>", unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════
# ANALYSE & APPROVE  — PDF fix: stored in session, shown outside analysis block
# ═════════════════════════════════════════════════════════════
elif menu == "Analyse & Approve":
    st.markdown("<div class='section-bar'>🔬 Analyse & Approve Exceptions</div>", unsafe_allow_html=True)
    st.markdown("<div class='info-box'>Select a pending exception, run AI analysis, "
                "fill approver details and submit decision. "
                "PDF report is generated on approval and stays available for download.</div>",
                unsafe_allow_html=True)

    # ── PDF download always visible at top when available ──────
    if st.session_state.get("pdf_bytes") and st.session_state.get("pdf_filename"):
        st.markdown("<div class='pdf-ready'>"
                    "<span style='font-size:20px'>📄</span><br>"
                    "<b style='font-size:15px'>Approval Report Ready</b><br>"
                    "<span style='font-size:12px;color:#276749'>Click below to download the PDF</span>"
                    "</div>", unsafe_allow_html=True)
        st.download_button(
            label     = "📥 Download Approval Report (PDF)",
            data      = st.session_state["pdf_bytes"],
            file_name = st.session_state["pdf_filename"],
            mime      = "application/pdf",
            key       = "dl_pdf_top",
            type      = "primary",
            use_container_width=True,
        )
        if st.button("✖ Clear PDF", key="clear_pdf"):
            st.session_state.pop("pdf_bytes",None)
            st.session_state.pop("pdf_filename",None)
            st.rerun()
        st.markdown("---")

    pending_df = get_pending()

    if pending_df.empty:
        st.info("✅ No pending exceptions at this time.")
    else:
        st.markdown(f"**{len(pending_df)} exception(s) awaiting review**")
        disp_cols = [c for c in [
            "exception_id","description","category","business_unit","asset_name",
            "risk_level","risk_score","recommendation","asset_criticality",
            "business_impact","compliance_impact","threat_exposure",
            "duration_days","requested_by","created_date"
        ] if c in pending_df.columns]
        st.dataframe(pending_df[disp_cols], use_container_width=True)

        st.markdown("---")
        st.markdown("### 🔬 Analyse an Exception")
        sel_id = st.selectbox("Select Exception ID", pending_df["exception_id"].tolist())

        if sel_id:
            row   = pending_df[pending_df["exception_id"]==sel_id].iloc[0]
            color = rc(row["risk_level"])

            if st.button("🔍 Run AI Analysis", type="primary", key="analyse_btn"):
                st.session_state["analysed_id"] = sel_id

            if st.session_state.get("analysed_id") == sel_id:
                desc = row["description"]
                with st.spinner("Running AI analysis..."):
                    category   = model.predict([desc])[0] if model else row.get("category","Unknown")
                    score_val  = int(row["risk_score"]) if pd.notna(row["risk_score"]) else 0
                    risk       = row["risk_level"]
                    rec_txt    = row["recommendation"] or risk_rec(risk)
                    history    = None
                    rec_dur    = int(row["duration_days"]) if pd.notna(row["duration_days"]) else 30
                    try:
                        history = get_historical_data(desc)
                        rec_dur = history["recommended_duration"]
                    except Exception:
                        pass

                st.markdown("#### 📋 AI Analysis Results")
                a1,a2,a3,a4 = st.columns(4)
                for col,lbl,val,clr in [
                    (a1,"Exception ID",    sel_id,              "#4f8ef7"),
                    (a2,"Category (AI)",   category,            "#4f8ef7"),
                    (a3,"Risk Level",      f"{risk} ({score_val})", color),
                    (a4,"Suggest Duration",f"{rec_dur} Days",   "#4f8ef7"),
                ]:
                    with col:
                        st.markdown(f"<div class='kpi-card' style='border-left-color:{clr}'>"
                                    f"<div class='kpi-label'>{lbl}</div>"
                                    f"<div class='kpi-value' style='font-size:17px;color:{clr}'>{val}</div>"
                                    f"</div>", unsafe_allow_html=True)

                st.markdown("#### 📄 Exception Details")
                st.dataframe(pd.DataFrame([
                    ("Description",       str(row.get("description","—"))),
                    ("Business Unit",     str(row.get("business_unit","—"))),
                    ("Asset Name",        str(row.get("asset_name","—"))),
                    ("Asset Criticality", str(row.get("asset_criticality","—"))),
                    ("Business Impact",   str(row.get("business_impact","—"))),
                    ("Compliance Impact", str(row.get("compliance_impact","—"))),
                    ("Threat Exposure",   str(row.get("threat_exposure","—"))),
                    ("Duration (Days)",   str(row.get("duration_days","—"))),
                    ("Requested By",      str(row.get("requested_by","—"))),
                    ("Risk Owner",        str(row.get("risk_owner","—"))),
                    ("Created Date",      str(row.get("created_date","—"))),
                    ("Recommendation",    str(rec_txt)),
                ], columns=["Field","Value"]), use_container_width=True, hide_index=True)

                if   risk=="Critical": st.error(  f"⚠️ {rec_txt}")
                elif risk=="High":     st.warning(f"⚠️ {rec_txt}")
                elif risk=="Medium":   st.info(   f"ℹ️ {rec_txt}")
                else:                  st.success(f"✅ {rec_txt}")

                if history:
                    st.markdown("#### 🕐 Historical Intelligence")
                    h1,h2,h3,h4,h5 = st.columns(5)
                    with h1: st.metric("Similar Requests", history["count"])
                    with h2: st.metric("Approved",         history["approved"])
                    with h3: st.metric("Rejected",         history["rejected"])
                    with h4: st.metric("Approval Rate",    f"{history['approval_rate']}%")
                    with h5: st.metric("Confidence",       history["confidence"])
                    exp_dt = datetime.today()+timedelta(days=rec_dur)
                    st.info(f"💡 Suggested Duration: **{rec_dur} Days** | "
                            f"Suggested Expiry: **{exp_dt.strftime('%d-%b-%Y')}** | "
                            f"Avg Historical: **{history.get('avg_duration','—')} Days** | "
                            f"Last Similar: **{history.get('last_date','—')}**")
                    # Source breakdown — shows how many matches came from each source
                    csv_m = history.get("csv_matches", 0)
                    db_m  = history.get("db_matches",  0)
                    st.caption(
                        f"📂 Matched from: **{csv_m:,}** synthetic training records "
                        f"+ **{db_m:,}** live database records = **{history['count']:,}** total"
                    )

                st.markdown("---")
                st.markdown("#### ✍️ Submit Decision")
                d1,d2,d3 = st.columns(3)
                with d1: appr_name  = st.text_input("Approver Full Name *", key="appr_name")
                with d2: appr_id    = st.text_input("Approver Employee ID",  key="appr_id")
                with d3: appr_title = st.text_input("Approver Title / Role",
                                                    placeholder="e.g. CISO, IT Manager",
                                                    key="appr_title")

                decision = st.selectbox("Decision",
                    ["Approved","Rejected","Under Review","Expired"], key="decision_sel")
                rej_reason = ""
                if decision=="Rejected":
                    rej_reason = st.text_area("Rejection Reason *", key="rej_reason")

                appr_display = appr_name.strip()
                if appr_id.strip():    appr_display += f" ({appr_id.strip()})"
                if appr_title.strip(): appr_display += f" — {appr_title.strip()}"

                if st.button("💾 Submit Decision", type="primary", key="submit_dec"):
                    if not appr_name.strip():
                        st.error("Please enter the approver name.")
                    elif decision=="Rejected" and not rej_reason.strip():
                        st.error("Please provide a rejection reason.")
                    else:
                        # 1. Save decision to DB
                        update_status(sel_id, decision,
                                      approved_by=appr_display,
                                      approver_id=appr_id.strip(),
                                      approver_title=appr_title.strip(),
                                      rejection_reason=rej_reason)

                        # 2. Generate PDF BEFORE rerun (while all variables are live)
                        if decision == "Approved":
                            try:
                                appr_dt  = datetime.now().strftime("%d-%b-%Y %H:%M:%S")
                                pdf_path = create_report(
                                    description        = desc,
                                    category           = category,
                                    score              = score_val,
                                    risk               = risk,
                                    history            = history,
                                    recommendation     = rec_txt,
                                    recommended_duration = rec_dur,
                                    exception_id       = sel_id,
                                    business_unit      = str(row.get("business_unit","—")),
                                    asset_name         = str(row.get("asset_name","—")),
                                    asset_criticality  = str(row.get("asset_criticality","—")),
                                    business_impact    = str(row.get("business_impact","—")),
                                    compliance_impact  = str(row.get("compliance_impact","—")),
                                    threat_exposure    = str(row.get("threat_exposure","—")),
                                    duration_days      = int(row.get("duration_days", rec_dur)),
                                    requested_by       = str(row.get("requested_by","—")),
                                    risk_owner         = str(row.get("risk_owner","—")),
                                    approver_name      = appr_name.strip(),
                                    approver_id        = appr_id.strip(),
                                    approver_title     = appr_title.strip(),
                                    approved_datetime  = appr_dt,
                                    decision           = decision,
                                )
                                with open(pdf_path,"rb") as f:
                                    st.session_state["pdf_bytes"]    = f.read()
                                st.session_state["pdf_filename"] = f"{sel_id}_Approval_Report.pdf"
                            except Exception as e:
                                st.session_state.pop("pdf_bytes",None)
                                st.warning(f"PDF generation error: {e}")

                        # 3. Clear analysis state, then rerun
                        #    PDF bytes are in session — will show at top of page
                        st.session_state.pop("analysed_id", None)
                        st.success(f"✅ Exception **{sel_id}** → **{decision}**. "
                                   + ("PDF ready at top of page." if decision=="Approved" else ""))
                        st.rerun()

# ═════════════════════════════════════════════════════════════
# ML RETRAINING
# ═════════════════════════════════════════════════════════════
elif menu == "ML Retraining":
    st.markdown("<div class='section-bar'>🤖 ML Model Retraining</div>", unsafe_allow_html=True)
    st.markdown("<div class='info-box'>Model improves by learning from <b>approved exceptions</b>. "
                "Minimum <b>50 new approved records</b> required per cycle.</div>",
                unsafe_allow_html=True)

    new_data = get_approved_for_ml()
    m1,m2,m3 = st.columns(3)
    conn_m = get_db()
    tot_appr = pd.read_sql_query("SELECT COUNT(*) as n FROM exceptions WHERE status='Approved'",conn_m).iloc[0,0]
    last_log = pd.read_sql_query("SELECT retrained_at,accuracy FROM ml_retrain_log ORDER BY id DESC LIMIT 1",conn_m)
    conn_m.close()
    with m1: st.metric("Total Approved in DB", tot_appr)
    with m2: st.metric("Pending Retraining",   len(new_data))
    with m3: st.metric("Last Accuracy", f"{float(last_log.iloc[0]['accuracy']):.2%}" if not last_log.empty else "—")

    st.markdown("---")
    conn_l=get_db()
    log_df=pd.read_sql_query("SELECT retrained_at,records_used,accuracy,notes FROM ml_retrain_log ORDER BY id DESC LIMIT 20",conn_l)
    conn_l.close()
    if not log_df.empty:
        st.markdown("#### Retraining History")
        st.dataframe(log_df, use_container_width=True)
    st.markdown("---")
    if len(new_data)>=50:
        if st.button("🚀 Retrain Model Now", type="primary"):
            with st.spinner("Retraining..."):
                ok,msg = attempt_retrain()
            (st.success if ok else st.error)(f"{'✅' if ok else '❌'} {msg}")
    else:
        st.warning(f"⏳ {len(new_data)} approved records available. Need 50 to retrain.")

# ═════════════════════════════════════════════════════════════
# DASHBOARD  — two-way pill toggle: Live ◀▶ ML
# ═════════════════════════════════════════════════════════════
elif menu == "Dashboard":

    df_csv     = pd.read_csv(DATASET_PATH)
    df_db      = get_all()
    risk_order = ["Critical","High","Medium","Low"]

    # ── Helper: render one row of cards ──────────────────────
    def kpi_row(cards):
        """cards = list of (cls, icon, label, value, sub)"""
        cols = st.columns(len(cards))
        for col,(cls,icon,lbl,val,sub) in zip(cols,cards):
            with col:
                st.markdown(
                    f"<div class='kpi-card {cls}'>"
                    f"<div class='kpi-label'>{icon} {lbl}</div>"
                    f"<div class='kpi-value'>{val}</div>"
                    f"<div class='kpi-sub'>{sub}</div></div>",
                    unsafe_allow_html=True)

    def kri_row(cards):
        """cards = list of (icon, label, value, sub)"""
        cols = st.columns(len(cards))
        for col,(icon,lbl,val,sub) in zip(cols,cards):
            with col:
                st.markdown(
                    f"<div class='kri-card'>"
                    f"<div class='kri-label'>{icon} {lbl}</div>"
                    f"<div class='kri-value'>{val}</div>"
                    f"<div class='kri-sub'>{sub}</div></div>",
                    unsafe_allow_html=True)

    # ── Dashboard toggle: Live (left) / ML (right) ───────────
    st.markdown(
        "<div style='background:var(--secondary-background-color);border-radius:10px;padding:14px 20px;"
        "box-shadow:0 4px 12px rgba(0,0,0,0.08);margin-bottom:18px;"
        "display:flex;align-items:center;gap:16px'>"
        "<span style='font-size:14px;font-weight:700;color:var(--text-color)'>Dashboard View</span>"
        "</div>", unsafe_allow_html=True)

    dash_live = st.toggle(
        "🗄️ Live Exception Data   ◀▶   📊 ML Training Data",
        value=False,
        key="dash_toggle",
        help="OFF = Live Exception Database  |  ON = ML Training Dataset"
    )

    # ── KPI / KRI selector: KPIs (left) / KRIs (right) ───────
    kpi_kri = st.toggle(
        "📈 Key Performance Indicators   ◀▶   ⚠️ Key Risk Indicators",
        value=False,
        key="kpikri_toggle",
        help="OFF = show KPIs  |  ON = show KRIs"
    )

    st.markdown("---")

    # ══════════════════════════════════════════════════════════
    if not dash_live:
        # ── LIVE EXCEPTION DATABASE ───────────────────────────
        st.markdown(
            "<div style='background:linear-gradient(90deg,#1a4731,#276749);"
            "border-radius:10px;padding:15px 22px;margin-bottom:16px'>"
            "<span style='color:white;font-size:18px;font-weight:700'>🗄️ Live Exception Database</span><br>"
            "<span style='color:#9ae6b4;font-size:12px'>"
            "Real-time view of all submitted, approved, pending and rejected exceptions</span>"
            "</div>", unsafe_allow_html=True)

        # Stats
        db_total    = len(df_db)
        db_pending  = len(df_db[df_db["status"]=="Pending"])          if not df_db.empty else 0
        db_approved = len(df_db[df_db["status"]=="Approved"])         if not df_db.empty else 0
        db_rejected = len(df_db[df_db["status"]=="Rejected"])         if not df_db.empty else 0
        db_critical = len(df_db[df_db["risk_level"]=="Critical"])     if not df_db.empty else 0
        db_high     = len(df_db[df_db["risk_level"]=="High"])         if not df_db.empty else 0
        db_medium   = len(df_db[df_db["risk_level"]=="Medium"])       if not df_db.empty else 0
        db_low      = len(df_db[df_db["risk_level"]=="Low"])          if not df_db.empty else 0
        db_avg_sc   = round(df_db["risk_score"].mean(),1)             if not df_db.empty and "risk_score"    in df_db.columns else 0
        db_avg_dur  = round(df_db["duration_days"].mean(),0)          if not df_db.empty and "duration_days" in df_db.columns else 0
        db_long     = len(df_db[df_db["duration_days"]>90])           if not df_db.empty and "duration_days" in df_db.columns else 0
        def pct(n): return round(100*n/db_total,1) if db_total else 0
        if not df_db.empty and "business_unit" in df_db.columns:
            _bu = df_db[df_db["risk_level"]=="Critical"].groupby("business_unit").size()
            db_top_bu = _bu.idxmax() if not _bu.empty else "—"
            db_top_n  = int(_bu.max()) if not _bu.empty else 0
        else:
            db_top_bu,db_top_n = "—",0

        if not kpi_kri:
            # KPIs
            st.markdown("<div class='section-bar'>📈 Key Performance Indicators — Live Database</div>",
                        unsafe_allow_html=True)
            kpi_row([
                ("total",   "🗄️","Total Records",  f"{db_total:,}",        "live submissions"),
                ("approved","✅","Approved",        f"{db_approved:,}",     f"{pct(db_approved)}% approval rate"),
                ("total",   "⏳","Pending",         f"{db_pending:,}",      f"{pct(db_pending)}% awaiting"),
                ("critical","❌","Rejected",        f"{db_rejected:,}",     f"{pct(db_rejected)}% rejected"),
                ("critical","🔴","Critical Risk",   f"{db_critical:,}",     f"{pct(db_critical)}% of total"),
                ("high",    "🟠","High Risk",       f"{db_high:,}",         f"{pct(db_high)}% of total"),
                ("total",   "📊","Avg Risk Score",  f"{db_avg_sc}",         "live average"),
                ("total",   "📅","Avg Duration",    f"{int(db_avg_dur)}d",  "average length"),
            ])
        else:
            # KRIs
            st.markdown("<div class='section-bar'>⚠️ Key Risk Indicators — Live Database</div>",
                        unsafe_allow_html=True)
            kri_row([
                ("🔴","Critical Rate",     f"{pct(db_critical)}%",   f"{db_critical} records"),
                ("⏳","Pending Rate",      f"{pct(db_pending)}%",    f"{db_pending} awaiting"),
                ("❌","Rejection Rate",    f"{pct(db_rejected)}%",   f"{db_rejected} declined"),
                ("📅","Long Dur >90d",     f"{pct(db_long)}%",       f"{db_long} records"),
                ("🏢","Top Risky BU",      db_top_bu,                f"{db_top_n} critical"),
            ])

        # Live records table
        st.markdown("<div class='section-bar'>🗃️ All Live Exception Records</div>",
                    unsafe_allow_html=True)
        if df_db.empty:
            st.info("No records yet. Submit an exception to get started.")
        else:
            fc1,fc2,fc3 = st.columns(3)
            with fc1:
                f_status = st.multiselect("Status",
                    sorted(df_db["status"].dropna().unique()), key="lf_status")
            with fc2:
                f_risk = st.multiselect("Risk Level",
                    ["Critical","High","Medium","Low"], key="lf_risk")
            with fc3:
                f_bu = st.multiselect("Business Unit",
                    sorted(df_db["business_unit"].dropna().unique()) if "business_unit" in df_db.columns else [],
                    key="lf_bu")
            vw = df_db.copy()
            if f_status: vw = vw[vw["status"].isin(f_status)]
            if f_risk:   vw = vw[vw["risk_level"].isin(f_risk)]
            if f_bu and "business_unit" in vw.columns: vw = vw[vw["business_unit"].isin(f_bu)]
            show_cols = [c for c in [
                "exception_id","description","category","business_unit","asset_name",
                "risk_level","risk_score","status","asset_criticality","business_impact",
                "compliance_impact","threat_exposure","duration_days","requested_by",
                "risk_owner","recommendation","approved_by","approver_title",
                "approved_datetime","created_date","expiry_date"
            ] if c in vw.columns]
            st.markdown(f"Showing **{len(vw):,}** of **{db_total:,}** records")
            st.dataframe(vw[show_cols], use_container_width=True)

        # Live charts
        if not df_db.empty and db_total >= 2:
            st.markdown("<div class='section-bar'>📊 Live Data Analytics</div>",
                        unsafe_allow_html=True)
            ch1,ch2 = st.columns(2)
            with ch1:
                dbrc = df_db["risk_level"].value_counts().reindex(risk_order).dropna().reset_index()
                dbrc.columns=["Risk_Level","Count"]
                f1=px.pie(dbrc,names="Risk_Level",values="Count",
                          color="Risk_Level",color_discrete_map=RISK_COLORS,
                          title="Risk Distribution",hole=0.45)
                f1.update_traces(textposition="outside",textinfo="percent+label",pull=[0.05,0.05,0,0])
                f1.update_layout(**CHART_LAYOUT)
                st.plotly_chart(f1, use_container_width=True)
            with ch2:
                dbsc=df_db["status"].value_counts().reset_index()
                dbsc.columns=["Status","Count"]
                f2=px.bar(dbsc,x="Status",y="Count",title="Exception Status",
                          color="Status",color_discrete_sequence=px.colors.qualitative.Set2)
                f2.update_layout(**CHART_LAYOUT)
                f2.update_xaxes(gridcolor="#f0f0f0"); f2.update_yaxes(gridcolor="#f0f0f0")
                st.plotly_chart(f2, use_container_width=True)

            ch3,ch4 = st.columns(2)
            with ch3:
                if "business_unit" in df_db.columns:
                    bu_db=df_db.groupby(["business_unit","risk_level"]).size().reset_index(name="Count")
                    bu_db["risk_level"]=pd.Categorical(bu_db["risk_level"],categories=risk_order,ordered=True)
                    f3=px.bar(bu_db.sort_values("risk_level"),x="business_unit",y="Count",
                              color="risk_level",barmode="group",
                              color_discrete_map=RISK_COLORS,
                              category_orders={"risk_level":risk_order},
                              title="Business Unit Risk Breakdown",
                              labels={"Count":"Exceptions","business_unit":"","risk_level":"Risk"})
                    f3.update_layout(**CHART_LAYOUT)
                    f3.update_xaxes(tickangle=-25,gridcolor="#f0f0f0")
                    f3.update_yaxes(gridcolor="#f0f0f0")
                    st.plotly_chart(f3, use_container_width=True)
            with ch4:
                if "risk_score" in df_db.columns:
                    f4=px.histogram(df_db,x="risk_score",color="risk_level",
                                    color_discrete_map=RISK_COLORS,nbins=20,
                                    title="Risk Score Distribution",
                                    labels={"risk_score":"Risk Score"})
                    f4.update_layout(**CHART_LAYOUT)
                    f4.update_xaxes(gridcolor="#f0f0f0"); f4.update_yaxes(gridcolor="#f0f0f0")
                    st.plotly_chart(f4, use_container_width=True)

            ch5,ch6 = st.columns(2)
            with ch5:
                if "category" in df_db.columns:
                    cat_db=df_db.groupby(["category","status"]).size().reset_index(name="Count")
                    f5=px.bar(cat_db,x="category",y="Count",color="status",barmode="stack",
                              title="Category vs Status",
                              labels={"Count":"Exceptions","category":""},
                              color_discrete_sequence=px.colors.qualitative.Pastel)
                    f5.update_layout(**CHART_LAYOUT)
                    f5.update_xaxes(tickangle=-25,gridcolor="#f0f0f0")
                    f5.update_yaxes(gridcolor="#f0f0f0")
                    st.plotly_chart(f5, use_container_width=True)
            with ch6:
                if "duration_days" in df_db.columns and "risk_score" in df_db.columns:
                    f6=px.scatter(df_db,x="duration_days",y="risk_score",
                                  color="risk_level",color_discrete_map=RISK_COLORS,
                                  title="Duration vs Risk Score",
                                  labels={"duration_days":"Duration (Days)",
                                          "risk_score":"Risk Score","risk_level":"Risk"},
                                  hover_data=["exception_id","status"])
                    f6.update_layout(**CHART_LAYOUT)
                    f6.update_xaxes(gridcolor="#f0f0f0"); f6.update_yaxes(gridcolor="#f0f0f0")
                    st.plotly_chart(f6, use_container_width=True)

    else:
        # ── ML TRAINING DATASET ───────────────────────────────
        st.markdown(
            "<div style='background:linear-gradient(90deg,#1a1f36,#2d3561);"
            "border-radius:10px;padding:15px 22px;margin-bottom:16px'>"
            "<span style='color:white;font-size:18px;font-weight:700'>📊 ML Training Dataset</span><br>"
            "<span style='color:#a0aec0;font-size:12px'>"
            "Analysis of the 100,000-record dataset used to train the AI classification model</span>"
            "</div>", unsafe_allow_html=True)

        # Stats
        csv_total   = len(df_csv)
        csv_appr    = len(df_csv[df_csv["Status"]=="Approved"])
        csv_pend    = len(df_csv[df_csv["Status"]=="Pending"])
        csv_rej     = len(df_csv[df_csv["Status"]=="Rejected"])
        csv_crit    = len(df_csv[df_csv["Risk_Level"]=="Critical"])
        csv_high    = len(df_csv[df_csv["Risk_Level"]=="High"])
        csv_med     = len(df_csv[df_csv["Risk_Level"]=="Medium"])
        csv_low     = len(df_csv[df_csv["Risk_Level"]=="Low"])
        csv_avg_sc  = round(df_csv["Risk_Score"].mean(),1)    if "Risk_Score"    in df_csv.columns else 0
        csv_avg_dur = round(df_csv["Duration_Days"].mean(),0) if "Duration_Days" in df_csv.columns else 0
        csv_long    = len(df_csv[df_csv["Duration_Days"]>90]) if "Duration_Days" in df_csv.columns else 0
        def cpct(n): return round(100*n/csv_total,1) if csv_total else 0
        if "Business_Unit" in df_csv.columns:
            _cbu     = df_csv[df_csv["Risk_Level"]=="Critical"].groupby("Business_Unit").size()
            csv_top_bu = _cbu.idxmax() if not _cbu.empty else "—"
            csv_top_n  = int(_cbu.max()) if not _cbu.empty else 0
        else:
            csv_top_bu,csv_top_n = "—",0

        if not kpi_kri:
            # KPIs
            st.markdown("<div class='section-bar'>📈 Key Performance Indicators — ML Training Dataset</div>",
                        unsafe_allow_html=True)
            kpi_row([
                ("total",   "📋","Total Records",  f"{csv_total:,}",        "training dataset"),
                ("approved","✅","Approved",        f"{csv_appr:,}",         f"{cpct(csv_appr)}% approval rate"),
                ("total",   "⏳","Pending",         f"{csv_pend:,}",         f"{cpct(csv_pend)}% of total"),
                ("critical","❌","Rejected",        f"{csv_rej:,}",          f"{cpct(csv_rej)}% rejected"),
                ("critical","🔴","Critical Risk",   f"{csv_crit:,}",         f"{cpct(csv_crit)}% of total"),
                ("high",    "🟠","High Risk",       f"{csv_high:,}",         f"{cpct(csv_high)}% of total"),
                ("total",   "📊","Avg Risk Score",  f"{csv_avg_sc}",         "out of 110 max"),
                ("total",   "📅","Avg Duration",    f"{int(csv_avg_dur)}d",  "average length"),
            ])
        else:
            # KRIs
            st.markdown("<div class='section-bar'>⚠️ Key Risk Indicators — ML Training Dataset</div>",
                        unsafe_allow_html=True)
            kri_row([
                ("🔴","Critical Rate",     f"{cpct(csv_crit)}%",  f"{csv_crit:,} records"),
                ("🟠","High Risk Rate",    f"{cpct(csv_high)}%",  f"{csv_high:,} records"),
                ("⏳","Pending Rate",      f"{cpct(csv_pend)}%",  f"{csv_pend:,} awaiting"),
                ("📅","Long Dur >90d",     f"{cpct(csv_long)}%",  f"{csv_long:,} records"),
                ("🏢","Top Risky BU",      csv_top_bu,             f"{csv_top_n} critical"),
            ])

        # ML Charts
        st.markdown("<div class='section-bar'>📊 Risk Distribution</div>", unsafe_allow_html=True)
        c1,c2 = st.columns([3,2])
        with c1:
            cat_risk=df_csv.groupby(["Category","Risk_Level"]).size().reset_index(name="Count")
            cat_risk["Risk_Level"]=pd.Categorical(cat_risk["Risk_Level"],categories=risk_order,ordered=True)
            f1=px.bar(cat_risk.sort_values("Risk_Level"),x="Category",y="Count",
                      color="Risk_Level",barmode="group",
                      color_discrete_map=RISK_COLORS,category_orders={"Risk_Level":risk_order},
                      title="Category & Risk Level",
                      labels={"Count":"Exceptions","Category":"","Risk_Level":"Risk Level"})
            f1.update_layout(**CHART_LAYOUT)
            f1.update_xaxes(tickangle=-25,gridcolor="#f0f0f0")
            f1.update_yaxes(gridcolor="#f0f0f0")
            st.plotly_chart(f1, use_container_width=True)
        with c2:
            rc2=df_csv["Risk_Level"].value_counts().reindex(risk_order).reset_index()
            rc2.columns=["Risk_Level","Count"]
            f2=px.pie(rc2,names="Risk_Level",values="Count",
                      color="Risk_Level",color_discrete_map=RISK_COLORS,
                      title="Overall Risk Distribution",hole=0.45)
            f2.update_traces(textposition="outside",textinfo="percent+label",pull=[0.05,0.05,0,0])
            f2.update_layout(**CHART_LAYOUT)
            st.plotly_chart(f2, use_container_width=True)

        st.markdown("<div class='section-bar'>🏢 Business Unit Analysis</div>", unsafe_allow_html=True)
        b1,b2 = st.columns([3,2])
        with b1:
            bu_risk=df_csv.groupby(["Business_Unit","Risk_Level"]).size().reset_index(name="Count")
            bu_risk["Risk_Level"]=pd.Categorical(bu_risk["Risk_Level"],categories=risk_order,ordered=True)
            f3=px.bar(bu_risk.sort_values("Risk_Level"),x="Business_Unit",y="Count",
                      color="Risk_Level",barmode="group",
                      color_discrete_map=RISK_COLORS,category_orders={"Risk_Level":risk_order},
                      title="Business Unit Risk Breakdown",
                      labels={"Count":"Exceptions","Business_Unit":"","Risk_Level":"Risk Level"})
            f3.update_layout(**CHART_LAYOUT)
            f3.update_xaxes(tickangle=-25,gridcolor="#f0f0f0"); f3.update_yaxes(gridcolor="#f0f0f0")
            st.plotly_chart(f3, use_container_width=True)
        with b2:
            bu_appr=(df_csv.groupby("Business_Unit")
                     .apply(lambda g: round(100*(g["Status"]=="Approved").sum()/len(g),1))
                     .reset_index(name="Approval_Rate")
                     .sort_values("Approval_Rate",ascending=True))
            f4=px.bar(bu_appr,x="Approval_Rate",y="Business_Unit",orientation="h",
                      title="Approval Rate by BU (%)",
                      labels={"Approval_Rate":"Approval Rate (%)","Business_Unit":""},
                      color="Approval_Rate",
                      color_continuous_scale=["#e53e3e","#dd6b20","#d69e2e","#38a169"])
            f4.update_layout(**CHART_LAYOUT,coloraxis_showscale=False)
            f4.update_xaxes(gridcolor="#f0f0f0",range=[0,100])
            st.plotly_chart(f4, use_container_width=True)

        st.markdown("<div class='section-bar'>📅 Pattern & Trend Analysis</div>", unsafe_allow_html=True)
        p1,p2 = st.columns(2)
        with p1:
            sc=df_csv.groupby(["Category","Status"]).size().reset_index(name="Count")
            f5=px.bar(sc,x="Category",y="Count",color="Status",barmode="stack",
                      title="Exception Status by Category",
                      labels={"Count":"Exceptions","Category":""},
                      color_discrete_sequence=px.colors.qualitative.Set2)
            f5.update_layout(**CHART_LAYOUT)
            f5.update_xaxes(tickangle=-25,gridcolor="#f0f0f0"); f5.update_yaxes(gridcolor="#f0f0f0")
            st.plotly_chart(f5, use_container_width=True)
        with p2:
            samp=df_csv.sample(min(2000,len(df_csv)),random_state=42)
            f6=px.scatter(samp,x="Duration_Days",y="Risk_Score",color="Risk_Level",
                          color_discrete_map=RISK_COLORS,opacity=0.5,
                          title="Duration vs Risk Score (2,000 sample)",
                          labels={"Duration_Days":"Duration (Days)","Risk_Score":"Risk Score",
                                  "Risk_Level":"Risk Level"})
            f6.update_layout(**CHART_LAYOUT)
            f6.update_xaxes(gridcolor="#f0f0f0"); f6.update_yaxes(gridcolor="#f0f0f0")
            st.plotly_chart(f6, use_container_width=True)

        st.markdown("<div class='section-bar'>📊 Distribution Histograms</div>", unsafe_allow_html=True)
        h1,h2 = st.columns(2)
        with h1:
            f7=px.histogram(df_csv,x="Risk_Score",color="Risk_Level",
                            color_discrete_map=RISK_COLORS,nbins=40,
                            title="Risk Score Distribution",
                            labels={"Risk_Score":"Risk Score"})
            f7.update_layout(**CHART_LAYOUT)
            f7.update_xaxes(gridcolor="#f0f0f0"); f7.update_yaxes(gridcolor="#f0f0f0")
            st.plotly_chart(f7, use_container_width=True)
        with h2:
            f8=px.histogram(df_csv,x="Duration_Days",color="Risk_Level",
                            color_discrete_map=RISK_COLORS,nbins=40,
                            title="Duration Distribution",
                            labels={"Duration_Days":"Duration (Days)"})
            f8.update_layout(**CHART_LAYOUT)
            f8.update_xaxes(gridcolor="#f0f0f0"); f8.update_yaxes(gridcolor="#f0f0f0")
            st.plotly_chart(f8, use_container_width=True)

        h3,h4 = st.columns(2)
        with h3:
            f9=px.histogram(df_csv,x="Asset_Criticality",color="Risk_Level",
                            color_discrete_map=RISK_COLORS,barmode="group",
                            title="Asset Criticality Distribution",
                            labels={"Asset_Criticality":"Asset Criticality"})
            f9.update_layout(**CHART_LAYOUT)
            f9.update_xaxes(gridcolor="#f0f0f0"); f9.update_yaxes(gridcolor="#f0f0f0")
            st.plotly_chart(f9, use_container_width=True)
        with h4:
            f10=px.histogram(df_csv,x="Business_Impact",color="Risk_Level",
                             color_discrete_map=RISK_COLORS,barmode="group",
                             title="Business Impact Distribution",
                             labels={"Business_Impact":"Business Impact"})
            f10.update_layout(**CHART_LAYOUT)
            f10.update_xaxes(gridcolor="#f0f0f0"); f10.update_yaxes(gridcolor="#f0f0f0")
            st.plotly_chart(f10, use_container_width=True)

        # Dataset table toggle
        st.markdown("<div class='section-bar'>🗃️ Training Dataset Records</div>",
                    unsafe_allow_html=True)
        show_ds = st.toggle("Show dataset records", value=False, key="show_ds_toggle")
        if show_ds:
            st.markdown(f"First 500 of **{csv_total:,}** records")
            st.dataframe(df_csv.head(500), use_container_width=True)

# ═════════════════════════════════════════════════════════════
# SEARCH EXCEPTION
# ═════════════════════════════════════════════════════════════
elif menu == "Search Exception":
    st.markdown("<div class='section-bar'>🔍 Search Exception Records</div>", unsafe_allow_html=True)

    search_source = st.radio("Search in:",
        ["📄 CSV Dataset (100,000 records)","🗄️ Live Database"], horizontal=True)

    if "CSV" in search_source:
        df=pd.read_csv(DATASET_PATH)
        cr,cs,cb,cc="Risk_Level","Status","Business_Unit","Category"
    else:
        df=get_all()
        cr,cs,cb,cc="risk_level","status","business_unit","category"

    kw=st.text_input("🔤 Keyword",placeholder="e.g. firewall  or  ERP  or  EX000123",key="se_kw")
    sc1,sc2,sc3,sc4=st.columns(4)
    with sc1: s_cat=st.multiselect("Category",   sorted(df[cc].dropna().unique()) if cc in df.columns else [],key="se_cat")
    with sc2: s_risk=st.multiselect("Risk Level", ["Critical","High","Medium","Low"],key="se_risk")
    with sc3: s_stat=st.multiselect("Status",     sorted(df[cs].dropna().unique()) if cs in df.columns else [],key="se_stat")
    with sc4: s_bu=st.multiselect("Business Unit",sorted(df[cb].dropna().unique()) if cb in df.columns else [],key="se_bu")

    st.markdown("<br>",unsafe_allow_html=True)
    sb1,sb2,_=st.columns([1,1,5])
    with sb1: search_go   = st.button("🔍 Search",type="primary",use_container_width=True,key="se_go")
    with sb2: search_reset= st.button("🔄 Reset", use_container_width=True,key="se_reset")

    if search_reset:
        for k in ["se_kw","se_cat","se_risk","se_stat","se_bu","se_results"]:
            st.session_state.pop(k,None)
        st.rerun()

    if search_go:
        filt=df.copy()
        if kw.strip():
            mask=pd.Series(False,index=filt.index)
            for col in filt.columns:
                mask=mask|filt[col].astype(str).str.contains(kw.strip(),case=False,na=False,regex=False)
            filt=filt[mask]
        if s_cat  and cc in filt.columns: filt=filt[filt[cc].isin(s_cat)]
        if s_risk and cr in filt.columns: filt=filt[filt[cr].isin(s_risk)]
        if s_stat and cs in filt.columns: filt=filt[filt[cs].isin(s_stat)]
        if s_bu   and cb in filt.columns: filt=filt[filt[cb].isin(s_bu)]
        st.session_state["se_results"]=filt

    st.markdown("---")
    results=st.session_state.get("se_results",None)
    if results is not None:
        if len(results)==0:
            st.warning("No records matched. Try a shorter keyword.")
        else:
            st.success(f"✅ Found **{len(results):,}** matching record(s)")
            m1,m2,m3,m4=st.columns(4)
            for col,lvl in zip([m1,m2,m3,m4],["Critical","High","Medium","Low"]):
                with col:
                    cnt=len(results[results[cr]==lvl])
                    st.markdown(
                        f"<div class='kpi-card' style='border-left-color:{RISK_COLORS[lvl]};padding:12px 15px'>"
                        f"<div class='kpi-label'>{lvl}</div>"
                        f"<div class='kpi-value' style='font-size:22px;color:{RISK_COLORS[lvl]}'>{cnt:,}</div>"
                        f"</div>",unsafe_allow_html=True)
            st.markdown("<br>",unsafe_allow_html=True)
            st.dataframe(results, use_container_width=True)
    else:
        st.info("👆 Set filters above and click **🔍 Search**.")
