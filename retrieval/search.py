from typing import Any

import chromadb

from retrieval.ingest import ensure_ingested


def _client() -> chromadb.ClientAPI:
    return ensure_ingested()


def _hits(results: dict[str, Any]) -> list[dict[str, Any]]:
    documents = results["documents"][0] or []
    metadatas = results["metadatas"][0] or []
    distances = results.get("distances", [[]])[0] or []
    ids = results["ids"][0] or []
    return [
        {
            "id": ids[index],
            "text": documents[index],
            "metadata": metadatas[index],
            "distance": distances[index] if index < len(distances) else None,
        }
        for index in range(len(documents))
    ]


def plain_rag(query: str, k: int = 3) -> list[dict[str, Any]]:
    if k < 1:
        raise ValueError("k must be at least 1")
    collection = _client().get_collection("reg_chunks")
    return _hits(collection.query(query_texts=[query], n_results=k))


def two_step_rag(query: str, k: int = 3) -> list[dict[str, Any]]:
    if k < 1:
        raise ValueError("k must be at least 1")
    client = _client()
    section_results = client.get_collection("reg_sections").query(
        query_texts=[query],
        n_results=2,
    )
    section_metadatas = section_results["metadatas"][0] or []
    top_sections = list(
        dict.fromkeys(
            metadata["section_path"]
            for metadata in section_metadatas
            if "section_path" in metadata
        )
    )
    if not top_sections:
        return []

    chunk_results = client.get_collection("reg_chunks").query(
        query_texts=[query],
        n_results=k,
        where={"section_path": {"$in": top_sections}},
    )
    return _hits(chunk_results)
