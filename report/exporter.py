from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from docx import Document


_APPLICANT_FIELDS = (
    ("Applicant name", "applicant_name", "applicant_name_page"),
    ("Employment type", "employment_type", "employment_type_page"),
    ("Monthly income (INR)", "monthly_income_inr", "monthly_income_page"),
    ("Requested loan (INR)", "loan_amount_inr", "loan_amount_page"),
    ("Tenure (months)", "tenure_months", "tenure_page"),
    ("Credit score", "credit_score", "credit_score_page"),
    ("Existing monthly EMIs (INR)", "existing_monthly_emi_inr", "existing_emi_page"),
)


def build_executive_memo(
    state: dict[str, Any],
    reviewer_name: str = "",
    reviewer_notes: str = "",
) -> bytes:
    document = Document()
    document.add_heading("Executive Credit Review Memo", level=0)

    parsed_doc = state.get("parsed_doc", {})
    document.add_paragraph(f"Source document: {parsed_doc.get('filename', 'Unknown')}")
    document.add_paragraph(
        f"Document type: {state.get('doc_type', 'Unknown').title()}"
    )

    document.add_heading("Extracted Applicant Details", level=1)
    application = state.get("loan_application")
    if application:
        table = document.add_table(rows=1, cols=3)
        table.style = "Light Shading Accent 1"
        header = table.rows[0].cells
        header[0].text = "Field"
        header[1].text = "Value"
        header[2].text = "Source page"
        for label, field, page_field in _APPLICANT_FIELDS:
            if field not in application:
                continue
            cells = table.add_row().cells
            cells[0].text = label
            cells[1].text = str(application[field])
            page = application.get(page_field)
            cells[2].text = str(page) if page is not None else "Not recorded"
    else:
        document.add_paragraph("No structured applicant fields were provided.")

    document.add_heading("Financial Ratios and Risk Assessment", level=1)
    risk_result = state.get("risk_result")
    if risk_result:
        ratios = risk_result.get("ratios", {})
        laya = risk_result.get("laya", {})
        document.add_paragraph(
            f"Proposed EMI: INR {ratios.get('proposed_emi_inr', 'N/A')}"
        )
        document.add_paragraph(
            f"EMI-to-income: {ratios.get('emi_to_income', 'N/A')}"
        )
        document.add_paragraph(f"DTI ratio: {ratios.get('dti_ratio', 'N/A')}")
        if ratios.get("ltv_ratio") is not None:
            document.add_paragraph(f"LTV ratio: {ratios['ltv_ratio']}")
        document.add_paragraph(
            f"Risk badge: Laya {laya.get('label', 'N/A')} "
            f"(confidence {laya.get('confidence', 'N/A')}) | "
            f"Rules {ratios.get('rule_risk', 'N/A')} | "
            f"Final {risk_result.get('final_risk', 'N/A')}"
        )
        if risk_result.get("escalate"):
            document.add_paragraph(
                f"Escalation reason: {risk_result.get('escalation_reason') or 'Not specified'}"
            )
    else:
        document.add_paragraph("No financial risk assessment was provided.")

    explanation = state.get("explanation", {})
    document.add_heading("Compliance Findings", level=1)
    summary = explanation.get("summary_markdown", "").strip()
    if summary:
        for line in summary.splitlines():
            text = line.strip()
            if not text:
                continue
            if text.startswith("#"):
                document.add_heading(text.lstrip("# ").strip(), level=2)
            else:
                document.add_paragraph(text)
    else:
        document.add_paragraph("No compliance findings were provided.")

    document.add_heading("Verbatim RBI Citations", level=1)
    cited_ids = set(explanation.get("cited_regulation_ids", []))
    cited_pages = explanation.get("cited_doc_pages", [])
    document.add_paragraph(
        "Cited document pages: "
        + (", ".join(str(page) for page in cited_pages) if cited_pages else "None")
    )
    seen_citations: set[str] = set()
    for evidence in state.get("regulation_context", []):
        metadata = evidence.get("metadata", {})
        regulation_id = metadata.get("para_id")
        if regulation_id not in cited_ids or regulation_id in seen_citations:
            continue
        seen_citations.add(regulation_id)
        document.add_paragraph(
            f"{metadata.get('section_path', 'RBI direction')} — {regulation_id}",
            style="Heading 2",
        )
        document.add_paragraph(evidence.get("text", ""))
    missing_ids = cited_ids - seen_citations
    for regulation_id in sorted(missing_ids):
        document.add_paragraph(
            f"{regulation_id}: citation text was not present in the retrieved context."
        )
    if not cited_ids:
        document.add_paragraph("No regulation paragraph IDs were cited.")

    document.add_heading("Human Reviewer Decision", level=1)
    status = state.get("human_review_status", "awaiting_review")
    decision_label = {
        "approved": "Approved",
        "rejected": "Rejected",
        "overridden": "Overridden",
    }.get(status, str(status).replace("_", " ").title())
    reviewer_timestamp = state.get("reviewer_timestamp") or datetime.now(
        timezone.utc
    ).isoformat(timespec="seconds")
    review_table = document.add_table(rows=4, cols=2)
    review_table.style = "Light Shading Accent 1"
    review_rows = (
        ("Decision", decision_label),
        ("Reviewer", reviewer_name or state.get("reviewer_name") or "Not recorded"),
        ("Reviewer timestamp (UTC)", reviewer_timestamp),
        ("Reviewer notes", reviewer_notes or state.get("reviewer_notes") or "None"),
    )
    for row, (label, value) in zip(review_table.rows, review_rows):
        row.cells[0].text = label
        row.cells[1].text = str(value)

    output = BytesIO()
    document.save(output)
    return output.getvalue()


def save_executive_memo(state: dict[str, Any], output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(build_executive_memo(state))
    return path
