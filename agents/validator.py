from __future__ import annotations

from collections.abc import Callable, Collection, Mapping
from typing import TYPE_CHECKING, Any

import chromadb

from agents.explainer import ExplanationOutput
from retrieval.ingest import CHROMA_DIR

if TYPE_CHECKING:
    from parsers.parse import ParsedDocument


def validate_citations(
    parsed_doc: ParsedDocument | Mapping[str, Any],
    cited_doc_pages: list[int],
    cited_regulation_ids: list[str],
    reg_chunk_ids: Collection[str],
) -> bool:
    pages = (
        parsed_doc.pages
        if hasattr(parsed_doc, "pages")
        else parsed_doc["pages"]
    )
    available_pages = {int(page) for page in pages}
    available_regulation_ids = set(reg_chunk_ids)
    return all(page in available_pages for page in cited_doc_pages) and all(
        regulation_id in available_regulation_ids
        for regulation_id in cited_regulation_ids
    )


def validate_and_regenerate(
    parsed_doc: ParsedDocument | Mapping[str, Any],
    explanation: ExplanationOutput,
    reg_chunk_ids: Collection[str],
    regenerate: Callable[[], ExplanationOutput],
) -> tuple[ExplanationOutput, bool]:
    if validate_citations(
        parsed_doc,
        explanation.cited_doc_pages,
        explanation.cited_regulation_ids,
        reg_chunk_ids,
    ):
        return explanation, True

    regenerated = regenerate()
    is_valid = validate_citations(
        parsed_doc,
        regenerated.cited_doc_pages,
        regenerated.cited_regulation_ids,
        reg_chunk_ids,
    )
    return regenerated, is_valid


def get_regulation_ids() -> set[str]:
    if not CHROMA_DIR.exists():
        raise FileNotFoundError(
            f"Chroma database not found at {CHROMA_DIR}. "
            "Run `python -m retrieval.ingest` first."
        )
    collection = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(
        "reg_chunks"
    )
    return set(collection.get()["ids"])


def run_gate_check() -> None:
    from parsers.parse import ParsedDocument

    if not CHROMA_DIR.exists():
        raise FileNotFoundError(
            f"Chroma database not found at {CHROMA_DIR}. "
            "Run `python -m retrieval.ingest` first."
        )
    collection = chromadb.PersistentClient(path=str(CHROMA_DIR)).get_collection(
        "reg_chunks"
    )
    reg_chunk_ids = set(collection.get()["ids"])
    parsed_doc = ParsedDocument(
        filename="gate-check.docx",
        total_pages=1,
        pages={1: "Example source page"},
        full_tagged_text="=== [PAGE 1] ===\nExample source page\n=== [END PAGE 1] ===",
    )
    invalid_pages = [99]
    invalid_regulation_ids = ["RBI-99.9"]
    invalid = ExplanationOutput(
        summary_markdown="Invalid citations for gate test.",
        cited_doc_pages=invalid_pages,
        cited_regulation_ids=invalid_regulation_ids,
    )
    assert not validate_citations(
        parsed_doc, invalid_pages, invalid_regulation_ids, reg_chunk_ids
    )

    regeneration_calls = 0

    def regenerate() -> ExplanationOutput:
        nonlocal regeneration_calls
        regeneration_calls += 1
        return ExplanationOutput(
            summary_markdown="Regenerated explanation.",
            cited_doc_pages=[1],
            cited_regulation_ids=[],
        )

    regenerated, is_valid = validate_and_regenerate(
        parsed_doc, invalid, reg_chunk_ids, regenerate
    )
    assert regeneration_calls == 1
    assert is_valid
    assert regenerated.cited_doc_pages == [1]
    print("Citation validator gate passed; invalid citations triggered regeneration.")


if __name__ == "__main__":
    run_gate_check()
