def get_decision_recommendation(
    risk,
    approval_rate
):

    if risk == "Critical":

        if approval_rate < 30:
            return "Reject Exception"

        return "Escalate to CISO"

    elif risk == "High":

        if approval_rate > 70:
            return "Approve With Compensating Controls"

        return "Management Review Required"

    elif risk == "Medium":

        return "Management Approval Required"

    else:

        return "Approve Exception"