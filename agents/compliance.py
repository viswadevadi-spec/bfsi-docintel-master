import json
from pathlib import Path
from typing import Any

from retrieval.search import plain_rag, two_step_rag


PROJECT_ROOT = Path(__file__).resolve().parents[1]
QUESTIONS_PATH = PROJECT_ROOT / "eval" / "rag_questions.json"


def evaluate_retrievers(
    questions: list[dict[str, str]], k: int = 3
) -> dict[str, dict[str, float | int]]:
    plain_hits = 0
    section_hits = 0
    for question in questions:
        expected = question["expected_section_path"]
        plain_results = plain_rag(question["question"], k=k)
        section_results = two_step_rag(question["question"], k=k)
        plain_hits += any(
            result["metadata"].get("section_path") == expected
            for result in plain_results
        )
        section_hits += any(
            result["metadata"].get("section_path") == expected
            for result in section_results
        )

    total = len(questions)
    if total == 0:
        raise ValueError("No RAG questions were provided for evaluation.")
    return {
        "plain": {
            "hits": plain_hits,
            "total": total,
            "hit_rate": plain_hits / total * 100,
        },
        "section_aware": {
            "hits": section_hits,
            "total": total,
            "hit_rate": section_hits / total * 100,
        },
    }


def main() -> None:
    with QUESTIONS_PATH.open("r", encoding="utf-8") as questions_file:
        questions: list[dict[str, Any]] = json.load(questions_file)
    results = evaluate_retrievers(questions)
    plain = results["plain"]
    section_aware = results["section_aware"]
    print(
        f"Plain RAG Hit Rate: {plain['hits']}/{plain['total']} "
        f"({plain['hit_rate']:.1f}%)"
    )
    print(
        f"Section-Aware RAG Hit Rate: {section_aware['hits']}/"
        f"{section_aware['total']} ({section_aware['hit_rate']:.1f}%)"
    )


if __name__ == "__main__":
    main()
