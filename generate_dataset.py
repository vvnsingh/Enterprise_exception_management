import pandas as pd
import random
from datetime import datetime, timedelta

NUM_RECORDS = 100000

templates_df = pd.read_csv("exception_templates.csv")

# =====================================================
# DESCRIPTION VARIATION POOLS
# =====================================================

actions = [
    "required", "requested", "needed", "initiated",
    "submitted", "raised", "approved", "proposed",
    "scheduled", "recommended", "triggered",
    "generated", "created", "authorized", "reviewed"
]

purposes = [
    "testing", "maintenance", "deployment",
    "migration", "integration", "upgrade",
    "troubleshooting", "validation",
    "vendor onboarding", "application rollout",
    "cloud transition", "system enhancement",
    "performance optimization",
    "business continuity",
    "security review"
]

systems = [
    "application", "server", "database",
    "web portal", "cloud platform",
    "network device", "security appliance",
    "API gateway", "vendor system",
    "business service", "mail server",
    "ERP platform", "CRM solution",
    "backup server", "identity platform"
]

urgency = [
    "critical",
    "high priority",
    "medium priority",
    "low priority",
    "business urgent",
    "time sensitive",
    "operationally required",
    "project driven"
]

justifications = [
    "to support business operations",
    "to meet project timelines",
    "to complete migration activities",
    "to support vendor connectivity",
    "to resolve technical issues",
    "to improve service availability",
    "to enable production deployment",
    "to facilitate integration activities"
]

locations = [
    "production environment",
    "test environment",
    "cloud environment",
    "corporate network",
    "branch office",
    "data center",
    "SOC platform",
    "vendor network",
    "development environment",
    "disaster recovery site"
]

projects = [
    "ERP Modernization",
    "Cloud Migration",
    "Zero Trust Program",
    "SOC Upgrade",
    "Infrastructure Refresh",
    "Business Transformation",
    "Digital Initiative",
    "Application Upgrade",
    "Network Expansion",
    "Compliance Program"
]

business_units = [
    "IT", "Security", "Finance", "HR",
    "Operations", "Legal", "Procurement",
    "Projects", "Cloud", "SOC", "DevOps",
    "Audit", "Compliance", "Research",
    "Infrastructure", "Network", "Application",
    "Data Management", "Business Continuity",
    "Administration"
]

assets = [
    "ERP Server", "Finance Server", "HR Server",
    "Active Directory", "Database Server",
    "Cloud Portal", "AWS Account",
    "Azure Subscription", "Firewall",
    "VPN Gateway", "SIEM Platform",
    "Email Gateway", "Web Application",
    "API Gateway", "Kubernetes Cluster",
    "DevOps Pipeline", "PKI Infrastructure",
    "DLP Server", "Core Router",
    "Analytics Platform"
]

# =====================================================
# DESCRIPTION GENERATOR  (no #N suffixes)
# =====================================================

def generate_description(base_template):
    """
    Generate a natural language exception description from a base template.
    The base_template must be a clean string with NO trailing #N sequence.
    """
    style = random.randint(1, 5)

    if style == 1:
        return (
            f"{base_template} "
            f"{random.choice(actions)} "
            f"for {random.choice(purposes)} "
            f"of {random.choice(systems)} "
            f"in {random.choice(locations)} "
            f"under {random.choice(urgency)} conditions "
            f"for {random.choice(projects)} "
            f"{random.choice(justifications)}."
        )

    elif style == 2:
        return (
            f"Request submitted for "
            f"{base_template.lower()} "
            f"to support "
            f"{random.choice(projects)} "
            f"in the "
            f"{random.choice(locations)}."
        )

    elif style == 3:
        return (
            f"{random.choice(business_units)} team "
            f"requires "
            f"{base_template.lower()} "
            f"for "
            f"{random.choice(purposes)} "
            f"activities involving "
            f"{random.choice(systems)}."
        )

    elif style == 4:
        return (
            f"Temporary exception requested "
            f"for "
            f"{base_template.lower()} "
            f"during "
            f"{random.choice(projects)} "
            f"to support "
            f"{random.choice(justifications)}."
        )

    else:
        return (
            f"{base_template} "
            f"has been "
            f"{random.choice(actions)} "
            f"for "
            f"{random.choice(systems)} "
            f"located in "
            f"{random.choice(locations)} "
            f"for "
            f"{random.choice(projects)}."
        )

# =====================================================
# DATASET GENERATION
# =====================================================

records = []

for i in range(1, NUM_RECORDS + 1):

    template = templates_df.sample(1).iloc[0]

    # Template Description is already clean (no #N suffix)
    description = generate_description(
        template["Description"]
    )

    asset_criticality   = random.choice(["Low", "Medium", "High"])
    business_impact     = random.choice(["Low", "Medium", "High"])
    compliance_impact   = random.choice(["Low", "Medium", "High"])
    threat_exposure     = random.choice(["Low", "Medium", "High"])
    duration            = random.randint(5, 180)

    score = 0
    score += {"Low": 10, "Medium": 20, "High": 40}[asset_criticality]
    score += {"Low": 10, "Medium": 20, "High": 30}[business_impact]
    score += {"Low":  5, "Medium": 10, "High": 20}[compliance_impact]
    score += {"Low":  5, "Medium": 10, "High": 20}[threat_exposure]

    if duration > 90:
        score += 10

    if   score >= 90: risk = "Critical"
    elif score >= 70: risk = "High"
    elif score >= 40: risk = "Medium"
    else:             risk = "Low"

    recommendation = {
        "Critical": "Immediate Review Required",
        "High":     "Approve With Compensating Controls",
        "Medium":   "Management Approval Required",
        "Low":      "Standard Approval"
    }[risk]

    created = datetime.now() - timedelta(days=random.randint(1, 730))
    expiry  = created + timedelta(days=duration)

    records.append({
        "Exception_ID":       f"EX{i:06d}",
        "Description":        description,
        "Category":           template["Category"],
        "Business_Unit":      random.choice(business_units),
        "Asset_Name":         random.choice(assets),
        "Asset_Criticality":  asset_criticality,
        "Business_Impact":    business_impact,
        "Compliance_Impact":  compliance_impact,
        "Threat_Exposure":    threat_exposure,
        "Requested_By":       f"EMP_{random.randint(1000, 9999)}",
        "Risk_Owner":         f"MGR_{random.randint(100, 999)}",
        "Duration_Days":      duration,
        "Risk_Score":         score,
        "Risk_Level":         risk,
        "Recommendation":     recommendation,
        "Status":             random.choice([
                                  "Approved", "Pending",
                                  "Rejected", "Expired",
                                  "Under Review"
                              ]),
        "Created_Date":       created.date(),
        "Expiry_Date":        expiry.date()
    })

# =====================================================
# SAVE DATASET
# =====================================================

df = pd.DataFrame(records)

unique_count = df["Description"].nunique()
print(f"Unique Descriptions : {unique_count:,}")
print(f"Total Records       : {len(df):,}")
print(f"Uniqueness Rate     : {100 * unique_count / len(df):.1f}%")

df.to_csv("exception_dataset_100000.csv", index=False)
print("Dataset saved → exception_dataset_100000.csv")
