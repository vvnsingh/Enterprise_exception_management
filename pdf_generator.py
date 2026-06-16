from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime, timedelta


# ─────────────────────────────────────────────────────────────
# COLOUR PALETTE
# ─────────────────────────────────────────────────────────────
RISK_COLORS = {
    "Critical": colors.HexColor("#e53e3e"),
    "High":     colors.HexColor("#dd6b20"),
    "Medium":   colors.HexColor("#d69e2e"),
    "Low":      colors.HexColor("#38a169"),
}

HEADER_BG  = colors.HexColor("#1a1f36")
SECTION_BG = colors.HexColor("#edf2f7")
ACCENT     = colors.HexColor("#4f8ef7")
TEXT_DARK  = colors.HexColor("#1a202c")
TEXT_LIGHT = colors.HexColor("#718096")
WHITE      = colors.white


# ─────────────────────────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────────────────────────
def _styles():
    base   = getSampleStyleSheet()
    custom = {
        "DocTitle": ParagraphStyle(
            "DocTitle", parent=base["Normal"],
            fontSize=12, fontName="Helvetica-Bold",
            textColor=WHITE, alignment=TA_CENTER, spaceAfter=0, leading=15
        ),
        "DocSubtitle": ParagraphStyle(
            "DocSubtitle", parent=base["Normal"],
            fontSize=8, fontName="Helvetica",
            textColor=colors.HexColor("#a0aec0"),
            alignment=TA_CENTER, spaceAfter=0, leading=11
        ),
        "SectionHead": ParagraphStyle(
            "SectionHead", parent=base["Normal"],
            fontSize=10, fontName="Helvetica-Bold",
            textColor=ACCENT, spaceBefore=12, spaceAfter=3
        ),
        "FieldLabel": ParagraphStyle(
            "FieldLabel", parent=base["Normal"],
            fontSize=8, fontName="Helvetica-Bold",
            textColor=TEXT_LIGHT
        ),
        "FieldValue": ParagraphStyle(
            "FieldValue", parent=base["Normal"],
            fontSize=9, fontName="Helvetica",
            textColor=TEXT_DARK
        ),
        "Footer": ParagraphStyle(
            "Footer", parent=base["Normal"],
            fontSize=7, fontName="Helvetica",
            textColor=TEXT_LIGHT, alignment=TA_CENTER
        ),
        "RiskBadge": ParagraphStyle(
            "RiskBadge", parent=base["Normal"],
            fontSize=11, fontName="Helvetica-Bold",
            textColor=WHITE, alignment=TA_CENTER
        ),
        "Description": ParagraphStyle(
            "Description", parent=base["Normal"],
            fontSize=9, fontName="Helvetica",
            textColor=TEXT_DARK, leading=13
        ),
    }
    return base, custom


# ─────────────────────────────────────────────────────────────
# TWO-COLUMN DETAIL TABLE
# ─────────────────────────────────────────────────────────────
def _two_col_table(rows, col_widths=(65*mm, 105*mm)):
    _, custom = _styles()
    data = [
        [Paragraph(str(lbl), custom["FieldLabel"]),
         Paragraph(str(val), custom["FieldValue"])]
        for lbl, val in rows
    ]
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("ROWBACKGROUNDS", (0, 0), (-1, -1),
         [WHITE, colors.HexColor("#f7fafc")]),
        ("GRID",           (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
        ("VALIGN",         (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",     (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 4),
        ("LEFTPADDING",    (0, 0), (-1, -1), 7),
        ("RIGHTPADDING",   (0, 0), (-1, -1), 7),
    ]))
    return t


# ─────────────────────────────────────────────────────────────
# MAIN REPORT FUNCTION
# ─────────────────────────────────────────────────────────────
def create_report(
    description,
    category,
    score,
    risk,
    history,
    recommendation,
    recommended_duration,
    exception_id      = "—",
    business_unit     = "—",
    asset_name        = "—",
    asset_criticality = "—",
    business_impact   = "—",
    compliance_impact = "—",
    threat_exposure   = "—",
    duration_days     = None,
    requested_by      = "—",
    risk_owner        = "—",
    approver_name     = "—",
    approver_id       = "—",
    approver_title    = "—",
    approved_datetime = None,
    decision          = "Approved",
):
    pdf_file = f"{exception_id}_Approval_Report.pdf"

    doc = SimpleDocTemplate(
        pdf_file,
        leftMargin=18*mm, rightMargin=18*mm,
        topMargin=12*mm,  bottomMargin=16*mm
    )

    base, custom = _styles()
    content      = []

    risk_color       = RISK_COLORS.get(risk, ACCENT)
    expiry_dt        = datetime.today() + timedelta(days=recommended_duration)
    report_dt        = datetime.now().strftime("%d-%b-%Y  %H:%M:%S")
    approved_display = approved_datetime or report_dt

    # ── HEADER: single table, two rows, no inter-row line ────
    hdr = Table(
        [
            [Paragraph("AI Exception Management System", custom["DocTitle"])],
            [Paragraph("Exception Approval Report  ·  Confidential", custom["DocSubtitle"])],
        ],
        colWidths=[174*mm]
    )
    hdr.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), HEADER_BG),
        ("TOPPADDING",    (0, 0), (0, 0),   10),   # title row top
        ("BOTTOMPADDING", (0, 0), (0, 0),   2),    # title row bottom (tight gap)
        ("TOPPADDING",    (0, 1), (0, 1),   0),    # subtitle row top (flush)
        ("BOTTOMPADDING", (0, 1), (0, 1),   10),   # subtitle row bottom
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        # No GRID — removes the dividing line completely
    ]))
    content.append(hdr)
    content.append(Spacer(1, 8))

    # ── RISK BADGE + EXCEPTION ID ────────────────────────────
    badge = Table(
        [[
            Paragraph(f"{risk.upper()}  RISK", custom["RiskBadge"]),
            Paragraph(
                f"<b>Exception ID:</b>  {exception_id}<br/>"
                f"<b>Decision:</b>  {decision}<br/>"
                f"<b>Approved On:</b>  {approved_display}",
                custom["FieldValue"]
            ),
        ]],
        colWidths=[50*mm, 124*mm]
    )
    badge.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, 0), risk_color),
        ("BACKGROUND",    (1, 0), (1, 0), SECTION_BG),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LEFTPADDING",   (0, 0), (-1, -1), 10),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 10),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#e2e8f0")),
    ]))
    content.append(badge)
    content.append(Spacer(1, 10))

    # ── SECTION 1 — EXCEPTION DETAILS ───────────────────────
    content.append(Paragraph("1.  Exception Details", custom["SectionHead"]))
    content.append(HRFlowable(width="100%", thickness=0.4,
                              color=colors.HexColor("#e2e8f0")))
    content.append(Spacer(1, 4))

    content.append(Paragraph("Description", custom["FieldLabel"]))
    content.append(Spacer(1, 2))
    desc_tbl = Table(
        [[Paragraph(description, custom["Description"])]],
        colWidths=[174*mm]
    )
    desc_tbl.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f7fafc")),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.HexColor("#e2e8f0")),
    ]))
    content.append(desc_tbl)
    content.append(Spacer(1, 6))

    content.append(_two_col_table([
        ("Exception ID",    exception_id),
        ("Category (AI)",   category),
        ("Business Unit",   business_unit),
        ("Asset Name",      asset_name),
        ("Requested By",    requested_by),
        ("Risk Owner",      risk_owner),
        ("Duration (Days)", str(duration_days) if duration_days else str(recommended_duration)),
        ("Created Date",    datetime.today().strftime("%d-%b-%Y")),
        ("Expiry Date",     expiry_dt.strftime("%d-%b-%Y")),
    ]))
    content.append(Spacer(1, 10))

    # ── SECTION 2 — RISK ASSESSMENT ─────────────────────────
    content.append(Paragraph("2.  Risk Assessment", custom["SectionHead"]))
    content.append(HRFlowable(width="100%", thickness=0.4,
                              color=colors.HexColor("#e2e8f0")))
    content.append(Spacer(1, 4))
    content.append(_two_col_table([
        ("Risk Score",        str(score)),
        ("Risk Level",        risk),
        ("Asset Criticality", asset_criticality),
        ("Business Impact",   business_impact),
        ("Compliance Impact", compliance_impact),
        ("Threat Exposure",   threat_exposure),
        ("Recommendation",    recommendation),
    ]))
    content.append(Spacer(1, 10))

    # ── SECTION 3 — HISTORICAL INTELLIGENCE (optional) ───────
    if history:
        content.append(Paragraph("3.  Historical Intelligence", custom["SectionHead"]))
        content.append(HRFlowable(width="100%", thickness=0.4,
                                  color=colors.HexColor("#e2e8f0")))
        content.append(Spacer(1, 4))
        content.append(_two_col_table([
            ("Similar Requests Found", str(history.get("count",      "—"))),
            ("Previously Approved",    str(history.get("approved",   "—"))),
            ("Previously Rejected",    str(history.get("rejected",   "—"))),
            ("Approval Rate",          f"{history.get('approval_rate','—')}%"),
            ("Confidence Level",       str(history.get("confidence", "—"))),
            ("Average Duration",       f"{history.get('avg_duration','—')} Days"),
            ("Last Similar Request",   str(history.get("last_date",  "—"))),
        ]))
        content.append(Spacer(1, 10))

    # ── SECTION 4 — AI RECOMMENDATION ───────────────────────
    sec = 4 if history else 3
    content.append(Paragraph(f"{sec}.  AI Recommendation", custom["SectionHead"]))
    content.append(HRFlowable(width="100%", thickness=0.4,
                              color=colors.HexColor("#e2e8f0")))
    content.append(Spacer(1, 4))
    content.append(_two_col_table([
        ("Recommended Action",    recommendation),
        ("Suggested Duration",    f"{recommended_duration} Days"),
        ("Suggested Expiry Date", expiry_dt.strftime("%d-%b-%Y")),
    ]))
    content.append(Spacer(1, 10))

    # ── SECTION 5 — APPROVAL DETAILS ────────────────────────
    sec += 1
    content.append(Paragraph(f"{sec}.  Approval Details", custom["SectionHead"]))
    content.append(HRFlowable(width="100%", thickness=0.4,
                              color=colors.HexColor("#e2e8f0")))
    content.append(Spacer(1, 4))
    content.append(_two_col_table([
        ("Decision",           decision),
        ("Approver Name",      approver_name),
        ("Approver ID",        approver_id    if approver_id    else "—"),
        ("Approver Title",     approver_title if approver_title else "—"),
        ("Approved Date/Time", approved_display),
    ]))
    content.append(Spacer(1, 14))

    # ── SIGNATURE BLOCK ──────────────────────────────────────
    sig = Table(
        [[
            Paragraph(
                f"<b>Approved By:</b>  {approver_name}"
                + (f"  ({approver_id})"    if approver_id    else "")
                + (f"  —  {approver_title}" if approver_title else ""),
                custom["FieldValue"]
            ),
            Paragraph(
                f"<b>Date &amp; Time:</b>  {approved_display}",
                custom["FieldValue"]
            ),
        ]],
        colWidths=[100*mm, 74*mm]
    )
    sig.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), colors.HexColor("#f0fff4")),
        ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#c6f6d5")),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
        ("RIGHTPADDING",  (0, 0), (-1, -1), 8),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
    ]))
    content.append(sig)
    content.append(Spacer(1, 16))

    # ── FOOTER ───────────────────────────────────────────────
    content.append(HRFlowable(width="100%", thickness=0.4,
                              color=colors.HexColor("#e2e8f0")))
    content.append(Spacer(1, 4))
    content.append(Paragraph(
        f"Report generated by AI Exception Management System  ·  {report_dt}  ·  "
        f"Exception ID: {exception_id}  ·  CONFIDENTIAL — For authorised personnel only",
        custom["Footer"]
    ))

    doc.build(content)
    return pdf_file
