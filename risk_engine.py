def calculate_risk(
    asset,
    impact,
    duration,
    compliance_impact,
    threat_exposure,
):
    """
    Deterministic weighted risk scoring formula — 0 to 100 scale.

    Inputs
    ------
    asset              : Asset Criticality  – "High" | "Medium" | "Low"
    impact             : Business Impact    – "High" | "Medium" | "Low"
    duration           : Duration in days   – integer
    compliance_impact  : Compliance Impact  – "High" | "Medium" | "Low"
    threat_exposure    : Threat Exposure    – "High" | "Medium" | "Low"

    Fixed Point Weights (max total = 100)
    --------------------------------------
    Asset Criticality : High=30, Medium=20, Low=10
    Business Impact   : High=25, Medium=15, Low=8
    Compliance Impact : High=20, Medium=10, Low=5
    Threat Exposure   : High=15, Medium=8,  Low=4
    Duration          : >90 days=10, 46–90 days=7, <=45 days=5

    Risk Levels
    -----------
    Critical : score >= 90
    High     : score >= 70
    Medium   : score >= 40
    Low      : score <  40

    No model inference involved. Formula is entirely transparent and
    produces consistent, auditable output for every submission.
    """

    score = 0

    # Asset Criticality
    if asset == "High":
        score += 30
    elif asset == "Medium":
        score += 20
    else:                       # Low
        score += 10

    # Business Impact
    if impact == "High":
        score += 25
    elif impact == "Medium":
        score += 15
    else:                       # Low
        score += 8

    # Compliance Impact
    if compliance_impact == "High":
        score += 20
    elif compliance_impact == "Medium":
        score += 10
    else:                       # Low
        score += 5

    # Threat Exposure
    if threat_exposure == "High":
        score += 15
    elif threat_exposure == "Medium":
        score += 8
    else:                       # Low
        score += 4

    # Duration
    if duration > 90:
        score += 10
    elif duration > 45:
        score += 7
    else:                       # <= 45 days
        score += 5

    # Risk Level
    if score >= 90:
        level = "Critical"
    elif score >= 70:
        level = "High"
    elif score >= 40:
        level = "Medium"
    else:
        level = "Low"

    return score, level
