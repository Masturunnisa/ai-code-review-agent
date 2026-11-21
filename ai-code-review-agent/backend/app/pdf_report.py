from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Table,
    TableStyle,
)


def _safe_text(value: object) -> str:
    return escape(str(value or "").encode("latin-1", "replace").decode("latin-1"))


def create_pdf_report(analysis: dict) -> bytes:
    output = BytesIO()
    document = SimpleDocTemplate(
        output,
        pagesize=letter,
        rightMargin=0.65 * inch,
        leftMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title=f"Code Review Report - {analysis['filename']}",
        author="AI Code Review & Security Analysis Agent",
    )
    base = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "ReportTitle",
        parent=base["Title"],
        textColor=colors.HexColor("#18324b"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=base["Heading2"],
        textColor=colors.HexColor("#176f70"),
        spaceBefore=12,
        spaceAfter=6,
    )
    body_style = ParagraphStyle(
        "ReportBody",
        parent=base["BodyText"],
        leading=14,
        spaceAfter=5,
    )
    code_style = ParagraphStyle(
        "ReportCode",
        parent=base["Code"],
        fontName="Courier",
        fontSize=8,
        leading=10,
        backColor=colors.HexColor("#f2f5f8"),
        borderPadding=6,
        spaceAfter=7,
    )

    summary = analysis["summary"]
    findings = analysis.get("findings", [])
    elements = [
        Paragraph("Code Review Report", title_style),
        Paragraph(f"<b>Project:</b> {_safe_text(summary['project_name'])}", body_style),
        Paragraph(f"<b>File:</b> {_safe_text(analysis['filename'])}", body_style),
        Paragraph(f"<b>Language:</b> {_safe_text(analysis['language'])}", body_style),
        Paragraph(f"<b>Analyzed:</b> {_safe_text(analysis.get('analyzed_at', ''))}", body_style),
        Paragraph(
            "<b>Review status:</b> "
            f"{_safe_text(summary['review_status'])} &nbsp; "
            f"<b>Code quality score:</b> {summary['health_score']}/100",
            body_style,
        ),
        Paragraph(
            f"<b>Total issues detected:</b> {len(findings)}",
            body_style,
        ),
        Paragraph(
            "Submitted source is not embedded in this report to reduce accidental "
            "disclosure of credentials or proprietary code.",
            body_style,
        ),
        Paragraph("Executive summary", heading_style),
        Paragraph(_safe_text(summary["overview"]), body_style),
        Paragraph("Severity breakdown", heading_style),
    ]

    breakdown = summary["severity_breakdown"]
    rows = [["Severity", "Findings"]]
    rows.extend(
        [severity.title(), str(breakdown[severity])]
        for severity in ("critical", "high", "medium", "low")
    )
    count_table = Table(rows, colWidths=[2.5 * inch, 1.2 * inch], hAlign="LEFT")
    count_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eaf2f3")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#18324b")),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d6e0e8")),
        ("ALIGN", (1, 1), (1, -1), "CENTER"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    elements.extend([
        count_table,
        Paragraph("Multidimensional code health", heading_style),
        Paragraph(
            "Scores summarize available static-check findings and analyzer coverage; "
            "they are not runtime or performance measurements.",
            body_style,
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
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#18324b")),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d6e0e8")),
            ("ALIGN", (1, 1), (1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7f9fb")]),
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
    for finding in findings:
        location = f"Line {finding['line']}" if finding.get("line") else "Line unavailable"
        severity = finding.get(
            "severity_level", finding.get("severity", "info")
        )
        elements.append(Paragraph(
            f"<b>{_safe_text(severity.title())}: "
            f"{_safe_text(finding.get('title'))}</b> "
            f"({_safe_text(finding.get('type'))}, {_safe_text(location)})",
            body_style,
        ))
        elements.append(Paragraph(
            f"<b>Why problematic:</b> {_safe_text(finding.get('explanation'))}",
            body_style,
        ))
        elements.append(Paragraph(
            f"<b>Recommended correction:</b> {_safe_text(finding.get('recommended_fix'))}",
            body_style,
        ))
        remediation = finding.get("remediation", {})
        corrected = remediation.get("corrected_code")
        if corrected:
            elements.append(Paragraph("<b>Illustrative corrected code:</b>", body_style))
            code_text = corrected.encode("latin-1", "replace").decode("latin-1")
            elements.append(Preformatted(code_text, code_style, maxLineLength=90))
            elements.append(Paragraph(
                f"<b>Why better:</b> {_safe_text(remediation.get('why_better'))}",
                body_style,
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
            elements.append(Paragraph(
                f"{index}. <b>{_safe_text(severity.title())}: "
                f"{_safe_text(finding.get('title'))}{_safe_text(location)}</b> — "
                f"{_safe_text(finding.get('recommended_fix'))}",
                body_style,
            ))
    else:
        elements.append(Paragraph("No corrections were prioritized.", body_style))
    elements.extend([
        Paragraph(
            "Apply critical and high-severity corrections first, then rerun the available "
            "static checks and validate changes with tests and human review.",
            body_style,
        ),
        Paragraph(
            f"<b>Analysis limitations:</b> {_safe_text(summary['limitations'])}",
            body_style,
        ),
    ])
    document.build(elements)
    return output.getvalue()
