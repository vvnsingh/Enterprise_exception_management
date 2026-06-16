def calculate_risk(
    asset,
    impact,
    duration
):

    score = 0

    if asset == "High":
        score += 40

    elif asset == "Medium":
        score += 25

    else:
        score += 10

    if impact == "High":
        score += 30

    elif impact == "Medium":
        score += 20

    else:
        score += 10

    if duration > 90:
        score += 30

    elif duration > 45:
        score += 20

    else:
        score += 10

    if score >= 90:
        level = "Critical"

    elif score >= 70:
        level = "High"

    elif score >= 40:
        level = "Medium"

    else:
        level = "Low"

    return score, level