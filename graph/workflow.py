import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Literal, TypedDict

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from agents.explainer import ExplanationOutput, generate_explanation
from agents.risk import evaluate_risk
from agents.validator import get_regulation_ids, validate_citations
from report.exporter import save_executive_memo
from retrieval.search import two_step_rag
from schemas.loan import LoanApplication


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINTS_PATH = PROJECT_ROOT / "checkpoints.sqlite"


class DocIntelState(TypedDict, total=False):
    doc_type: Literal["loan", "contract"]
    document_path: str
    parsed_doc: dict[str, Any]
    loan_application: dict[str, Any]
    query: str
    risk_result: dict[str, Any]
    regulation_context: list[dict[str, Any]]
    explanation: dict[str, Any]
    citations_valid: bool
    regeneration_count: int
    human_review_status: Literal[
        "awaiting_review", "approved", "rejected", "overridden"
    ]
    human_decision: str
    reviewer_name: str
    reviewer_notes: str
    reviewer_timestamp: str
    report_path: str
    report_id: str


def route_document(state: DocIntelState) -> Literal["loan", "contract"]:
    doc_type = state.get("doc_type")
    if doc_type not in {"loan", "contract"}:
        raise ValueError("doc_type must be either 'loan' or 'contract'.")
    return doc_type


def _parsed_document(state: DocIntelState) -> dict[str, Any]:
    parsed_doc = state.get("parsed_doc")
    if parsed_doc is not None:
        return parsed_doc
    document_path = state.get("document_path")
    if not document_path:
        raise ValueError("Provide parsed_doc or document_path in workflow state.")

    from parsers.parse import parse_file

    return parse_file(document_path).model_dump(mode="json")


def _retrieve_context(query: str) -> list[dict[str, Any]]:
    return two_step_rag(query, k=5)


def loan_analysis(state: DocIntelState) -> dict[str, Any]:
    parsed_doc = _parsed_document(state)
    loan_data = state.get("loan_application")
    if loan_data is None:
        raise ValueError(
            "loan_application is required for loan workflows; "
            "supply the extracted LoanApplication fields."
        )
    application = LoanApplication.model_validate(loan_data)
    risk_result = evaluate_risk(application).model_dump(mode="json")
    query = state.get("query") or (
        "microfinance household repayment obligations and loan disclosures"
    )
    return {
        "parsed_doc": parsed_doc,
        "risk_result": risk_result,
        "regulation_context": _retrieve_context(query),
        "regeneration_count": 0,
    }


def contract_analysis(state: DocIntelState) -> dict[str, Any]:
    parsed_doc = _parsed_document(state)
    query = state.get("query") or (
        "contract terms and relevant RBI lending disclosure obligations"
    )
    return {
        "parsed_doc": parsed_doc,
        "regulation_context": _retrieve_context(query),
        "regeneration_count": 0,
    }


def explain(state: DocIntelState) -> dict[str, Any]:
    explanation = generate_explanation(
        parsed_doc=state["parsed_doc"],
        regulation_context=state.get("regulation_context", []),
        risk_result=state.get("risk_result"),
    )
    return {"explanation": explanation.model_dump(mode="json")}


def validate_explanation(state: DocIntelState) -> dict[str, Any]:
    explanation = ExplanationOutput.model_validate(state["explanation"])
    is_valid = validate_citations(
        state["parsed_doc"],
        explanation.cited_doc_pages,
        explanation.cited_regulation_ids,
        get_regulation_ids(),
    )
    return {
        "citations_valid": is_valid,
        "human_review_status": "awaiting_review",
    }


def route_after_validation(state: DocIntelState) -> Literal[
    "human_review", "regenerate_explanation"
]:
    if state.get("citations_valid"):
        return "human_review"
    if state.get("regeneration_count", 0) < 1:
        return "regenerate_explanation"
    return "human_review"


def regenerate_explanation(state: DocIntelState) -> dict[str, Any]:
    explanation = generate_explanation(
        parsed_doc=state["parsed_doc"],
        regulation_context=state.get("regulation_context", []),
        risk_result=state.get("risk_result"),
        regeneration_instruction=(
            "The previous response cited pages or regulation IDs that failed "
            "deterministic validation. Regenerate using only page numbers and "
            "regulation IDs present in the supplied evidence."
        ),
    )
    return {
        "explanation": explanation.model_dump(mode="json"),
        "regeneration_count": state.get("regeneration_count", 0) + 1,
    }


def human_review(state: DocIntelState) -> dict[str, Any]:
    decision = state.get("human_decision")
    normalized_decision = (
        decision.strip().lower() if isinstance(decision, str) else ""
    )
    decision_status = {
        "approve": "approved",
        "approved": "approved",
        "reject": "rejected",
        "rejected": "rejected",
        "override": "overridden",
        "overridden": "overridden",
    }.get(normalized_decision)
    if decision_status is None:
        raise ValueError(
            "Set human_decision to Approved, Rejected, or Overridden before "
            "resuming the interrupted workflow."
        )
    return {
        "human_review_status": decision_status,
        "reviewer_timestamp": datetime.now(timezone.utc).isoformat(
            timespec="seconds"
        ),
    }


def export_report(state: DocIntelState) -> dict[str, Any]:
    report_id = re.sub(r"[^a-zA-Z0-9_-]", "", state.get("report_id", "review"))
    if not report_id:
        raise ValueError("report_id must contain at least one safe filename character.")
    report_path = PROJECT_ROOT / "report" / "exports" / f"{report_id}.docx"
    saved_path = save_executive_memo(state, report_path)
    return {"report_path": str(saved_path)}


_builder = StateGraph(DocIntelState)
_builder.add_node("loan_analysis", loan_analysis)
_builder.add_node("contract_analysis", contract_analysis)
_builder.add_node("explain", explain)
_builder.add_node("validate_explanation", validate_explanation)
_builder.add_node("regenerate_explanation", regenerate_explanation)
_builder.add_node("human_review", human_review)
_builder.add_node("report", export_report)
_builder.add_conditional_edges(
    START,
    route_document,
    {"loan": "loan_analysis", "contract": "contract_analysis"},
)
_builder.add_edge("loan_analysis", "explain")
_builder.add_edge("contract_analysis", "explain")
_builder.add_edge("explain", "validate_explanation")
_builder.add_conditional_edges(
    "validate_explanation",
    route_after_validation,
    {
        "human_review": "human_review",
        "regenerate_explanation": "regenerate_explanation",
    },
)
_builder.add_edge("regenerate_explanation", "validate_explanation")
_builder.add_edge("human_review", "report")
_builder.add_edge("report", END)

conn = sqlite3.connect(str(CHECKPOINTS_PATH), check_same_thread=False)
checkpointer = SqliteSaver(conn)
checkpointer.setup()
workflow = _builder.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_review"],
)
