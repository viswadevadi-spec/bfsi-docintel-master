import re
from pathlib import Path

import chromadb


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGULATIONS_FILE = (
    PROJECT_ROOT / "data" / "regulations" / "rbi_lending_guidelines.md"
)
CHROMA_DIR = PROJECT_ROOT / "chroma_db"

SECTION_PATTERN = re.compile(
    r"(?m)^# Section (.+?)\s*\n(.*?)(?=^# Section |\Z)",
    re.DOTALL,
)
PARAGRAPH_PATTERN = re.compile(
    r"(?m)^Para ([A-Za-z0-9.]+):\s*(.*?)(?=^Para [A-Za-z0-9.]+:|\Z)",
    re.DOTALL,
)


def parse_regulation_sections(
    markdown: str,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    sections = []
    chunks = []
    for match in SECTION_PATTERN.finditer(markdown):
        section_path = f"Section {match.group(1).strip()}"
        body = match.group(2).strip()
        summary_match = re.search(r"(?m)^Summary:\s*(.+)$", body)
        summary = summary_match.group(1).strip() if summary_match else ""

        paragraphs = []
        for paragraph_match in PARAGRAPH_PATTERN.finditer(body):
            para_id = paragraph_match.group(1)
            paragraph_text = " ".join(paragraph_match.group(2).split())
            text = f"Para {para_id}: {paragraph_text}"
            paragraphs.append(text)
            chunks.append(
                {
                    "id": f"RBI-{para_id}",
                    "text": text,
                    "section_path": section_path,
                    "para_id": f"RBI-{para_id}",
                }
            )

        sections.append(
            {
                "id": re.sub(r"[^a-z0-9]+", "-", section_path.lower()).strip("-"),
                "text": f"{section_path}\n{summary}",
                "section_path": section_path,
            }
        )

    if not sections or not chunks:
        raise ValueError(f"No sections or numbered paragraphs found in {REGULATIONS_FILE}")
    return sections, chunks


def _replace_collection(
    client: chromadb.ClientAPI,
    name: str,
    documents: list[str],
    ids: list[str],
    metadatas: list[dict[str, str]],
) -> None:
    if name in {collection.name for collection in client.list_collections()}:
        client.delete_collection(name)
    collection = client.create_collection(name=name)
    collection.add(documents=documents, ids=ids, metadatas=metadatas)


def ingest() -> tuple[int, int]:
    markdown = REGULATIONS_FILE.read_text(encoding="utf-8")
    sections, chunks = parse_regulation_sections(markdown)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    _replace_collection(
        client,
        "reg_sections",
        [item["text"] for item in sections],
        [item["id"] for item in sections],
        [{"section_path": item["section_path"]} for item in sections],
    )
    _replace_collection(
        client,
        "reg_chunks",
        [item["text"] for item in chunks],
        [item["id"] for item in chunks],
        [
            {"section_path": item["section_path"], "para_id": item["para_id"]}
            for item in chunks
        ],
    )
    return len(sections), len(chunks)


def main() -> None:
    section_count, chunk_count = ingest()
    print(
        f"Ingested {section_count} sections and {chunk_count} numbered "
        f"paragraphs into {CHROMA_DIR}"
    )


if __name__ == "__main__":
    main()
