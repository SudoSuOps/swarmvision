"""
SwarmView Task — MRI Demo Report Generator

Task: swarmview.mri.demo

Generates a realistic-looking MRI analysis PDF report.
This demonstrates the full job execution flow without requiring ML models.
"""

import hashlib
import io
import json
import random
from datetime import datetime, timezone
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    Image,
    HRFlowable,
)


# =============================================================================
# MOCK MRI ANALYSIS
# =============================================================================

def analyze_mri_scan(input_data: dict) -> dict:
    """
    Mock MRI analysis.

    In production, this would run actual ML inference.
    For the demo, we generate realistic-looking findings.
    """
    # Extract patient info from input or generate mock
    patient_id = input_data.get("patient_id", f"P{random.randint(10000, 99999)}")
    scan_type = input_data.get("scan_type", "Brain MRI T1-weighted")
    scan_date = input_data.get("scan_date", datetime.now().strftime("%Y-%m-%d"))

    # Generate mock findings
    findings = []
    risk_score = random.uniform(0.1, 0.9)

    if risk_score > 0.7:
        severity = "HIGH"
        findings.append({
            "region": "Left temporal lobe",
            "finding": "Hyperintense signal detected",
            "confidence": round(random.uniform(0.85, 0.98), 2),
            "recommendation": "Further evaluation recommended",
        })
        findings.append({
            "region": "Ventricular system",
            "finding": "Mild asymmetry observed",
            "confidence": round(random.uniform(0.70, 0.85), 2),
            "recommendation": "Monitor in follow-up",
        })
    elif risk_score > 0.4:
        severity = "MODERATE"
        findings.append({
            "region": "White matter",
            "finding": "Minor signal variation within normal limits",
            "confidence": round(random.uniform(0.75, 0.90), 2),
            "recommendation": "No immediate action required",
        })
    else:
        severity = "LOW"
        findings.append({
            "region": "Overall",
            "finding": "No significant abnormalities detected",
            "confidence": round(random.uniform(0.90, 0.99), 2),
            "recommendation": "Routine follow-up",
        })

    return {
        "patient_id": patient_id,
        "scan_type": scan_type,
        "scan_date": scan_date,
        "analysis_date": datetime.now(timezone.utc).isoformat(),
        "risk_score": round(risk_score, 3),
        "severity": severity,
        "findings": findings,
        "model_version": "swarmview.mri.demo.v1",
        "execution_node": input_data.get("_operator_ens", "unknown"),
    }


# =============================================================================
# PDF REPORT GENERATION
# =============================================================================

def generate_mri_report(
    analysis: dict,
    client_ens: str,
    operator_ens: str,
    job_id: str,
    poe_hash: str,
) -> bytes:
    """
    Generate a PDF report from MRI analysis.

    Returns PDF bytes.
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72,
    )

    styles = getSampleStyleSheet()

    # Custom styles
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=24,
        spaceAfter=12,
        textColor=colors.HexColor("#1a365d"),
    )

    heading_style = ParagraphStyle(
        "CustomHeading",
        parent=styles["Heading2"],
        fontSize=14,
        spaceBefore=18,
        spaceAfter=6,
        textColor=colors.HexColor("#2c5282"),
    )

    normal_style = styles["Normal"]

    # Build document
    elements = []

    # Header
    elements.append(Paragraph("SwarmVision Medical Analysis", title_style))
    elements.append(Paragraph("MRI Scan Report", styles["Heading2"]))
    elements.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#2c5282")))
    elements.append(Spacer(1, 12))

    # Report metadata
    meta_data = [
        ["Report ID:", job_id],
        ["Generated:", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")],
        ["Client:", client_ens],
        ["Processing Node:", operator_ens],
    ]
    meta_table = Table(meta_data, colWidths=[1.5 * inch, 4 * inch])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 20))

    # Patient info
    elements.append(Paragraph("Patient Information", heading_style))
    patient_data = [
        ["Patient ID:", analysis["patient_id"]],
        ["Scan Type:", analysis["scan_type"]],
        ["Scan Date:", analysis["scan_date"]],
        ["Analysis Date:", analysis["analysis_date"][:10]],
    ]
    patient_table = Table(patient_data, colWidths=[1.5 * inch, 4 * inch])
    patient_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(patient_table)
    elements.append(Spacer(1, 20))

    # Risk assessment
    elements.append(Paragraph("Risk Assessment", heading_style))

    severity = analysis["severity"]
    if severity == "HIGH":
        risk_color = colors.HexColor("#c53030")
    elif severity == "MODERATE":
        risk_color = colors.HexColor("#d69e2e")
    else:
        risk_color = colors.HexColor("#38a169")

    risk_data = [
        ["Risk Score:", f"{analysis['risk_score']:.1%}"],
        ["Severity:", severity],
    ]
    risk_table = Table(risk_data, colWidths=[1.5 * inch, 4 * inch])
    risk_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 11),
        ("TEXTCOLOR", (1, 1), (1, 1), risk_color),
        ("FONTNAME", (1, 1), (1, 1), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    elements.append(risk_table)
    elements.append(Spacer(1, 20))

    # Findings
    elements.append(Paragraph("Findings", heading_style))

    for i, finding in enumerate(analysis["findings"], 1):
        elements.append(Paragraph(
            f"<b>Finding {i}:</b> {finding['region']}",
            normal_style
        ))
        elements.append(Paragraph(
            f"<i>{finding['finding']}</i>",
            normal_style
        ))
        elements.append(Paragraph(
            f"Confidence: {finding['confidence']:.0%} | "
            f"Recommendation: {finding['recommendation']}",
            normal_style
        ))
        elements.append(Spacer(1, 10))

    elements.append(Spacer(1, 30))

    # Proof of Execution footer
    elements.append(HRFlowable(width="100%", thickness=1, color=colors.gray))
    elements.append(Spacer(1, 8))
    elements.append(Paragraph("Proof of Execution", heading_style))

    poe_data = [
        ["PoE Hash:", poe_hash[:32] + "..."],
        ["Model:", analysis["model_version"]],
        ["Protocol:", "SwarmVision v0.2"],
    ]
    poe_table = Table(poe_data, colWidths=[1.5 * inch, 4 * inch])
    poe_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("FONTNAME", (1, 0), (1, 0), "Courier"),
        ("TEXTCOLOR", (1, 0), (1, 0), colors.gray),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    elements.append(poe_table)

    elements.append(Spacer(1, 12))
    elements.append(Paragraph(
        "<i>This report was generated by SwarmVision distributed compute network. "
        "The Proof of Execution cryptographically attests to the authenticity of "
        "this analysis.</i>",
        ParagraphStyle("Disclaimer", parent=normal_style, fontSize=8, textColor=colors.gray)
    ))

    # Build PDF
    doc.build(elements)

    return buffer.getvalue()


# =============================================================================
# TASK HANDLER (called by SwarmAgent)
# =============================================================================

def execute_mri_demo(job_payload: dict, operator_ens: str, job_id: str) -> tuple[bytes, dict]:
    """
    Execute MRI demo task.

    Args:
        job_payload: Input data from client
        operator_ens: Operator ENS identity
        job_id: Job identifier

    Returns:
        Tuple of (pdf_bytes, analysis_dict)
    """
    # Get client ENS from payload
    client_ens = job_payload.get("_client_ens", "unknown.swarmvision.eth")

    # Add operator to payload for analysis
    job_payload["_operator_ens"] = operator_ens

    # Run analysis
    analysis = analyze_mri_scan(job_payload)

    # Compute preliminary hash for embedding in PDF
    # (actual PoE hash will be computed after PDF generation)
    prelim_hash = hashlib.sha256(json.dumps(analysis, sort_keys=True).encode()).hexdigest()

    # Generate PDF
    pdf_bytes = generate_mri_report(
        analysis=analysis,
        client_ens=client_ens,
        operator_ens=operator_ens,
        job_id=job_id,
        poe_hash=prelim_hash,
    )

    return pdf_bytes, analysis


if __name__ == "__main__":
    # Test generation
    pdf, analysis = execute_mri_demo(
        {"patient_id": "TEST001", "scan_type": "Brain MRI"},
        "rig1.swarmcompute.eth",
        "job_test123"
    )

    with open("test_report.pdf", "wb") as f:
        f.write(pdf)

    print(f"Generated test report: {len(pdf)} bytes")
    print(f"Analysis: {json.dumps(analysis, indent=2)}")
