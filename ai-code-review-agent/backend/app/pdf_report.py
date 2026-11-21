from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    KeepTogether,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#18324b")
TEAL = colors.HexColor("#176f70")
INK = colors.HexColor("#33475e")
MUTED = colors.HexColor("#65788d")
LIGHT = colors.HexColor("#f4f7f9")
BORDER = colors.HexColor("#dce5eb")


def _safe_text(value: object) -> str:
    return escape(str(value or "").encode("latin-1", "replace").decode("latin-1"))


def create_pdf_report(analysis: dict) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.82 * inch,
        bottomMargin=0.72 * inch,
        title=f"Code Review Report - {analysis['filename']}",
        author="AI Code Review & Security Analysis Agent",
    )
    base = getSampleStyleSheet()
    eyebrow_style = ParagraphStyle(
        "ReportEyebrow",
        parent=base["Normal"],
        textColor=TEAL,
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        spaceAfter=5,
    )
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=base["Title"],
        textColor=NAVY,
        alignment=TA_LEFT,
        fontName="Helvetica-Bold",
        fontSize=24,
        leading=27,
        spaceAfter=3,
    )
    subtitle_style = ParagraphStyle(
        "ReportSubtitle",
        parent=base["Normal"],
        textColor=MUTED,
        fontSize=9,
        leading=13,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=base["Heading2"],
        textColor=NAVY,
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        spaceBefore=14,
        spaceAfter=7,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=base["BodyText"],
        textColor=INK,
        fontSize=9,
        leading=13,
        spaceAfter=4,
    )
    small_style = ParagraphStyle(
        "ReportSmall",
        parent=body_style,
        textColor=MUTED,
        fontSize=7.5,
        leading=10,
    )
    white_style = ParagraphStyle(
        "ReportWhite",
        parent=body_style,
        textColor=colors.white,
        fontSize=9,
        leading=13,
    )
    score_style = ParagraphStyle(
        "ReportScore",
        parent=base["Normal"],
        textColor=NAVY,
        fontName="Helvetica-Bold",
        fontSize=23,
        leading=25,
        alignment=TA_LEFT,
    )
    code_style = ParagraphStyle(
        "ReportCode",
        parent=base["Code"],
        fontName="Courier",
        fontSize=7.5,
        leading=9.5,
        textColor=INK,
        backColor=LIGHT,
        borderPadding=7,
        spaceBefore=4,
        spaceAfter=6,
    )

    summary = analysis["summary"]
    findings = analysis.get("findings", [])
    report_status = str(summary.get("review_status", "Needs review"))
    status_color = (
        colors.HexColor("#a74553")
        if report_status == "Changes Requested"
        else colors.HexColor("#946b24")
        if report_status == "Needs Review"
        else colors.HexColor("#26744f")
    )
    score = int(summary.get("health_score", 0))
    analyzed_at = analysis.get("analyzed_at", "")

    def draw_page_chrome(canvas, doc):
        canvas.saveState()
        page_width, page_height = document.pagesize
        canvas.setFillColor(NAVY)
        canvas.rect(0, page_height - 0.17 * inch, page_width, 0.17 * inch, fill=1, stroke=0)
        canvas.setFillColor(TEAL)
        canvas.rect(0.65 * inch, page_height - 0.17 * inch, 0.48 * inch, 0.17 * inch, fill=1, stroke=0)
        canvas.setFillColor(NAVY)
        canvas.setFont("Helvetica-Bold", 8)
        canvas.drawString(0.65 * inch, page_height - 0.44 * inch, "REVIEWSTUDIO")
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        canvas.drawRightString(
            page_width - 0.65 * inch,
            page_height - 0.44 * inch,
            "CODE INTELLIGENCE  /  SECURITY REVIEW",
        )
        canvas.setStrokeColor(BORDER)
        canvas.setLineWidth(0.6)
        canvas.line(0.65 * inch, 0.53 * inch, page_width - 0.65 * inch, 0.53 * inch)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 7)
        footer_filename = str(analysis["filename"]).encode("latin-1", "replace").decode("latin-1")
        canvas.drawString(0.65 * inch, 0.36 * inch, f"Static analysis report  ·  {footer_filename}")
        canvas.drawRightString(page_width - 0.65 * inch, 0.36 * inch, f"Page {doc.page}")
        canvas.restoreState()

    score_card = Table(
        [
            [Paragraph(f"{score}<font size='10'> /100</font>", score_style)],
            [Paragraph("OVERALL CODE HEALTH", small_style)],
        ],
        colWidths=[1.58 * inch],
    )
    score_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.7, BORDER),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("LEFTPADDING", (0, 0), (-1, -1), 10),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (0, 0), 9),
        ("BOTTOMPADDING", (0, 0), (0, 0), 2),
        ("TOPPADDING", (0, 1), (0, 1), 0),
        ("BOTTOMPADDING", (0, 1), (0, 1), 8),
    ]))
    report_hero = Table(
        [[
            [
                Paragraph(
                    f"<font color='{status_color.hexval()}'><b>{_safe_text(report_status).upper()}</b></font>",
                    white_style,
                ),
                Spacer(1, 4),
                Paragraph(_safe_text(summary.get("overview", "")), white_style),
            ],
            score_card,
        ]],
        colWidths=[4.8 * inch, 1.58 * inch],
        hAlign="LEFT",
    )
    report_hero.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), NAVY),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#eaf2f3")),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (0, 0), 13),
        ("RIGHTPADDING", (0, 0), (0, 0), 13),
        ("TOPPADDING", (0, 0), (0, 0), 13),
        ("BOTTOMPADDING", (0, 0), (0, 0), 13),
        ("LEFTPADDING", (1, 0), (1, 0), 9),
        ("RIGHTPADDING", (1, 0), (1, 0), 9),
        ("TOPPADDING", (1, 0), (1, 0), 9),
        ("BOTTOMPADDING", (1, 0), (1, 0), 9),
    ]))

    total_findings = len(findings)
    metadata_rows = [
        [
            Paragraph(f"<b>PROJECT</b><br/>{_safe_text(summary.get('project_name', ''))}", body_style),
            Paragraph(f"<b>SOURCE FILE</b><br/>{_safe_text(analysis['filename'])}", body_style),
        ],
        [
            Paragraph(f"<b>LANGUAGE</b><br/>{_safe_text(analysis.get('language', 'unknown')).title()}", body_style),
            Paragraph(f"<b>ANALYZED</b><br/>{_safe_text(analyzed_at)}", body_style),
        ],
    ]
    metadata_table = Table(metadata_rows, colWidths=[3.19 * inch, 3.19 * inch], hAlign="LEFT")
    metadata_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.45, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))

    elements = [
        Paragraph("AI CODE REVIEW  /  REPORT", eyebrow_style),
        Paragraph("Code Review Report", title_style),
        Paragraph("Security findings, code health signals, and a prioritized remediation plan.", subtitle_style),
        report_hero,
        Spacer(1, 10),
        metadata_table,
        Spacer(1, 7),
        Paragraph(
            f"<b>{total_findings}</b> issue(s) detected. Submitted source is not embedded "
            "to reduce accidental disclosure of credentials or proprietary code.",
            small_style,
        ),
        Paragraph("Severity breakdown", heading_style),
    ]

    breakdown = summary["severity_breakdown"]
    severity_colors = {
        "critical": colors.HexColor("#a9324b"),
        "high": colors.HexColor("#ae5b3f"),
        "medium": colors.HexColor("#946b24"),
        "low": colors.HexColor("#4e829d"),
    }
    severity_cards = [
        [
            Paragraph(
                f"<font color='{severity_colors[severity].hexval()}'><b>{severity.upper()}</b></font>"
                f"<br/><font size='16'><b>{breakdown[severity]}</b></font>"
                f"<br/><font size='7'>finding(s)</font>",
                body_style,
            )
        ]
        for severity in ("critical", "high", "medium", "low")
    ]
    count_table = Table([severity_cards], colWidths=[1.595 * inch] * 4, hAlign="LEFT")
    count_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.6, BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.extend([
        count_table,
        Paragraph("Multidimensional code health", heading_style),
        Paragraph(
            "Scores summarize detected static-check findings and completed analyzer checks; "
            "they are not runtime or performance measurements.",
            small_style,
        ),
    ])
    dimensions = summary.get("health_dimensions", [])
    if dimensions:
        dimension_rows = [["Dimension", "Score", "Basis"]]
        dimension_rows.extend(
            [
                _safe_text(item.get("label", "")),
                f"{item.get('score', 0)}/100",
                _safe_text(item.get("detail", "")),
            ]
            for item in dimensions
        )
        dimension_table = Table(
            dimension_rows,
            colWidths=[1.55 * inch, 0.8 * inch, 3.8 * inch],
            repeatRows=1,
            hAlign="LEFT",
        )
        dimension_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf2f3")),
            ("TEXTCOLOR", (0, 0), (-1, 0), NAVY),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, BORDER),
            ("ALIGN", (1, 1), (1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("PADDING", (0, 0), (-1, -1), 7),
        ]))
        elements.append(dimension_table)
    elements.extend([
        Paragraph("Security summary", heading_style),
        Paragraph(_safe_text(summary["security_summary"]), body_style),
        Paragraph("Code quality summary", heading_style),
        Paragraph(_safe_text(summary["quality_summary"]), body_style),
        Paragraph("Findings and recommended corrections", heading_style),
    ])

    if not findings:
        elements.append(Paragraph("No findings were reported by the available checks.", body_style))
    for finding_index, finding in enumerate(findings, start=1):
        location = f"Line {finding['line']}" if finding.get("line") else "Line unavailable"
        severity = finding.get(
            "severity_level", finding.get("severity", "info")
        )
        severity_key = str(severity).lower().replace(" ", "_")
        severity_color = {
            "critical": colors.HexColor("#b33f55"),
            "error": colors.HexColor("#b33f55"),
            "high": colors.HexColor("#c66a4d"),
            "medium": colors.HexColor("#a77825"),
            "warning": colors.HexColor("#a77825"),
            "low": colors.HexColor("#4e829d"),
            "info": colors.HexColor("#6f8092"),
        }.get(severity_key, colors.HexColor("#6f8092"))
        finding_content = [
            Paragraph(
                f"<font color='{severity_color.hexval()}'><b>{_safe_text(severity.title()).upper()}</b></font>"
                f" &nbsp; <font color='#8090a1'>FINDING {finding_index:02d}</font>"
                f"<br/><b>{_safe_text(finding.get('title'))}</b>"
                f" &nbsp; <font color='#65788d'>({_safe_text(finding.get('type'))} · "
                f"{_safe_text(location)})</font>",
                body_style,
            ),
            Paragraph(
                f"<b>Why this matters:</b> {_safe_text(finding.get('explanation'))}",
                body_style,
            ),
            Paragraph(
                f"<b>Recommended correction:</b> {_safe_text(finding.get('recommended_fix'))}",
                body_style,
            ),
        ]
        finding_card = Table([[finding_content]], colWidths=[6.38 * inch], hAlign="LEFT")
        finding_card.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.white),
            ("BOX", (0, 0), (-1, -1), 0.55, BORDER),
            ("LINEBEFORE", (0, 0), (0, 0), 3, severity_color),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 9),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        elements.append(KeepTogether([finding_card, Spacer(1, 7)]))
        remediation = finding.get("remediation", {})
        corrected = remediation.get("corrected_code")
        if corrected:
            elements.append(Paragraph("<b>Illustrative corrected code</b>", small_style))
            code_text = corrected.encode("latin-1", "replace").decode("latin-1")
            elements.append(Preformatted(code_text, code_style, maxLineLength=90))
            elements.append(Paragraph(
                f"<b>Why better:</b> {_safe_text(remediation.get('why_better'))}",
                small_style,
            ))

    elements.extend([
        Paragraph("Prioritized recommendations", heading_style),
    ])
    priority_findings = summary.get("recommended_corrections", [])
    if priority_findings:
        for index, finding in enumerate(priority_findings, start=1):
            location = f" (line {finding['line']})" if finding.get("line") else ""
            severity = finding.get(
                "severity_level", finding.get("severity", "")
            )
            priority_card = Table(
                [[
                    Paragraph(f"{index:02d}", score_style),
                    Paragraph(
                        f"<b>{_safe_text(severity.title())}: "
                        f"{_safe_text(finding.get('title'))}{_safe_text(location)}</b><br/>"
                        f"{_safe_text(finding.get('recommended_fix'))}",
                        body_style,
                    ),
                ]],
                colWidths=[0.48 * inch, 5.9 * inch],
                hAlign="LEFT",
            )
            priority_card.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
                ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (0, 0), (0, 0), "CENTER"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]))
            elements.extend([priority_card, Spacer(1, 5)])
    else:
        elements.append(Paragraph("No corrections were prioritized.", body_style))
    limitation_card = Table(
        [[Paragraph(
            f"<b>Analysis limitations:</b> {_safe_text(summary['limitations'])}",
            body_style,
        )]],
        colWidths=[6.38 * inch],
        hAlign="LEFT",
    )
    limitation_card.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("BOX", (0, 0), (-1, -1), 0.45, BORDER),
        ("LEFTPADDING", (0, 0), (-1, -1), 9),
        ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    elements.extend([
        Paragraph(
            "Apply critical and high-severity corrections first, then rerun the available "
            "static checks and validate changes with tests and human review.",
            body_style,
        ),
        limitation_card,
    ])
    document.build(elements, onFirstPage=draw_page_chrome, onLaterPages=draw_page_chrome)
    return output.getvalue()
