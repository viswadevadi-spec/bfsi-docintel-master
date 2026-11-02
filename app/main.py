import hashlib
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import streamlit as st

from graph.workflow import workflow as app_graph
from schemas.loan import LoanApplication


def _parse_uploaded_document(path: Path) -> dict[str, Any]:
    from parsers.parse import parse_file

    return parse_file(path).model_dump(mode="json")


def _read_snapshot(config: dict[str, Any]) -> Any:
    return app_graph.get_state(config)


def _run_analysis(
    initial_state: dict[str, Any],
    config: dict[str, Any],
    status: Any,
) -> None:
    started_at = time.perf_counter()
    for update in app_graph.stream(
        initial_state,
        config=config,
        stream_mode="updates",
    ):
        for node in update:
            elapsed = time.perf_counter() - started_at
            if node in {"loan_analysis", "contract_analysis"}:
                status.update(
                    label=(
                        f"Risk scoring and regulation search finished "
                        f"({elapsed:.1f}s). Waiting for OpenRouter explanation..."
                    ),
                    state="running",
                    expanded=True,
                )
            elif node == "explain":
                status.update(
                    label=(
                        f"OpenRouter explanation received ({elapsed:.1f}s). "
                        "Checking citations..."
                    ),
                    state="running",
                    expanded=True,
                )
            elif node == "validate_explanation":
                valid = update[node].get("citations_valid", False)
                label = (
                    "Citations checked. Preparing underwriter review..."
                    if valid
                    else "Citations need correction. Retrying the explanation..."
                )
                status.update(label=label, state="running", expanded=True)
            elif node == "regenerate_explanation":
                status.update(
                    label="Retry received. Checking citations...",
                    state="running",
                    expanded=True,
                )


def _render_report(state: dict[str, Any]) -> None:
    report_path = state.get("report_path")
    if not report_path:
        return
    path = Path(report_path)
    if not path.is_file():
        st.error(f"The workflow completed, but the report file is missing: {path}")
        return
    st.success(f"Review complete: {state.get('human_review_status', 'unknown')}")
    st.download_button(
        "Download executive memo",
        data=path.read_bytes(),
        file_name=path.name,
        mime=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    )


def _render_human_gate(config: dict[str, Any], snapshot: Any) -> None:
    if snapshot.next != ("human_review",):
        if snapshot.values:
            _render_report(snapshot.values)
        return

    st.warning(
        "Escalated for Human Underwriter Review",
        icon="⚠️",
    )
    explanation = snapshot.values.get("explanation", {})
    summary = explanation.get("summary_markdown")
    if summary:
        st.markdown(summary)

    reviewer_name = st.text_input("Reviewer name", key="reviewer_name")
    reviewer_notes = st.text_area("Reviewer notes", key="reviewer_notes")
    approve_col, reject_col = st.columns(2)
    decision: str | None = None
    if approve_col.button("Approve", type="primary"):
        decision = "Approved"
    if reject_col.button("Reject"):
        decision = "Rejected"

    if decision is not None:
        app_graph.update_state(config, {"human_decision": decision})
        app_graph.update_state(
            config,
            {
                "reviewer_name": reviewer_name,
                "reviewer_notes": reviewer_notes,
            },
        )
        app_graph.invoke(None, config)
        st.rerun()


def _loan_application_form() -> dict[str, Any]:
    st.subheader("Applicant details")
    with st.form("loan_application"):
        applicant_name = st.text_input("Applicant name")
        employment_type = st.selectbox(
            "Employment type", ("salaried", "self_employed")
        )
        monthly_income = st.number_input(
            "Monthly income (INR)", min_value=1.0, value=50000.0, step=1000.0
        )
        monthly_income_page = st.number_input(
            "Income source page", min_value=1, value=1, step=1
        )
        existing_emi = st.number_input(
            "Existing monthly EMIs (INR)", min_value=0.0, value=0.0, step=500.0
        )
        existing_emi_page = st.number_input(
            "Existing EMI source page", min_value=1, value=1, step=1
        )
        loan_amount = st.number_input(
            "Requested loan amount (INR)",
            min_value=1.0,
            value=500000.0,
            step=10000.0,
        )
        loan_amount_page = st.number_input(
            "Loan amount source page", min_value=1, value=1, step=1
        )
        tenure = st.number_input(
            "Tenure (months)", min_value=1, value=60, step=1
        )
        tenure_page = st.number_input("Tenure source page", min_value=1, value=1, step=1)
        credit_score = st.number_input(
            "Credit score", min_value=0, max_value=900, value=720, step=1
        )
        credit_score_page = st.number_input(
            "Credit score source page", min_value=1, value=1, step=1
        )
        applicant_name_page = st.number_input(
            "Applicant name source page", min_value=1, value=1, step=1
        )
        employment_type_page = st.number_input(
            "Employment type source page", min_value=1, value=1, step=1
        )
        submitted = st.form_submit_button("Analyze document")
    if not submitted:
        return {}

    application = LoanApplication(
        applicant_name=applicant_name.strip(),
        applicant_name_page=applicant_name_page,
        monthly_income_inr=monthly_income,
        monthly_income_page=monthly_income_page,
        loan_amount_inr=loan_amount,
        loan_amount_page=loan_amount_page,
        tenure_months=tenure,
        tenure_page=tenure_page,
        credit_score=credit_score,
        credit_score_page=credit_score_page,
        existing_monthly_emi_inr=existing_emi,
        existing_emi_page=existing_emi_page,
        employment_type=employment_type,
        employment_type_page=employment_type_page,
    )
    return application.model_dump(mode="json")


def main() -> None:
    st.set_page_config(page_title="BFSI DocIntel", layout="wide")
    st.title("BFSI Document Intelligence")
    st.caption(
        "Review loan or contract documents with source-linked regulatory evidence."
    )
    uploaded_file = st.file_uploader(
        "Upload a DOCX or PDF",
        type=["docx", "pdf"],
    )
    doc_type = st.selectbox("Document type", ("loan", "contract"))

    if uploaded_file is None:
        st.info("Upload a document to begin.")
        return

    uploaded_bytes = uploaded_file.getvalue()
    thread_id = hashlib.sha256(uploaded_bytes).hexdigest()[:12]
    config = {"configurable": {"thread_id": thread_id}}
    (PROJECT_ROOT / "data" / "parsed").mkdir(parents=True, exist_ok=True)
    loan_application: dict[str, Any] = {}
    if doc_type == "loan":
        loan_application = _loan_application_form()

    snapshot = _read_snapshot(config)
    if loan_application:
        try:
            suffix = Path(uploaded_file.name).suffix.lower()
            if suffix not in {".docx", ".pdf"}:
                raise ValueError("Only DOCX and PDF documents are supported.")
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=suffix,
                    dir=PROJECT_ROOT / "data" / "parsed",
                    delete=False,
                ) as temporary_file:
                    temporary_file.write(uploaded_bytes)
                    temporary_path = Path(temporary_file.name)
                with st.status("Parsing uploaded document...", expanded=True) as status:
                    parsed_doc = _parse_uploaded_document(temporary_path)
                    status.update(
                        label="Document parsed. Starting analysis...",
                        state="complete",
                        expanded=False,
                    )
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)

            initial_state = {
                "doc_type": doc_type,
                "parsed_doc": parsed_doc,
                "loan_application": loan_application,
                "query": (
                    "microfinance household repayment obligations, risk and "
                    "key facts statement disclosures"
                ),
                "report_id": thread_id,
            }
            with st.status(
                "Running local risk scoring and regulation search...",
                expanded=True,
            ) as status:
                _run_analysis(initial_state, config, status)
                status.update(
                    label="Analysis ready. Preparing underwriter review...",
                    state="complete",
                    expanded=False,
                )
            snapshot = _read_snapshot(config)
        except Exception as error:
            st.error(f"Document analysis failed: {error}")
            st.exception(error)
            return

    elif doc_type == "contract" and st.button("Analyze contract"):
        try:
            suffix = Path(uploaded_file.name).suffix.lower()
            temporary_path = None
            try:
                with tempfile.NamedTemporaryFile(
                    suffix=suffix,
                    dir=PROJECT_ROOT / "data" / "parsed",
                    delete=False,
                ) as temporary_file:
                    temporary_file.write(uploaded_bytes)
                    temporary_path = Path(temporary_file.name)
                with st.status("Parsing uploaded document...", expanded=True) as status:
                    parsed_doc = _parse_uploaded_document(temporary_path)
                    status.update(
                        label="Document parsed. Starting analysis...",
                        state="complete",
                        expanded=False,
                    )
            finally:
                if temporary_path is not None:
                    temporary_path.unlink(missing_ok=True)

            initial_state = {
                "doc_type": "contract",
                "parsed_doc": parsed_doc,
                "query": "contract clauses and applicable RBI lending disclosures",
                "report_id": thread_id,
            }
            with st.status(
                "Searching regulations...",
                expanded=True,
            ) as status:
                _run_analysis(initial_state, config, status)
                status.update(
                    label="Analysis ready. Preparing underwriter review...",
                    state="complete",
                    expanded=False,
                )
            snapshot = _read_snapshot(config)
        except Exception as error:
            st.error(f"Contract analysis failed: {error}")
            st.exception(error)
            return

    _render_human_gate(config, snapshot)


if __name__ == "__main__":
    main()
