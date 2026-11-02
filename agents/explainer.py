import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import AuthenticationError, OpenAI
from pydantic import BaseModel, Field
import streamlit as st
from streamlit.errors import StreamlitSecretNotFoundError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _get_setting(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    try:
        return st.secrets.get(name, default)
    except StreamlitSecretNotFoundError:
        return default


class ExplanationOutput(BaseModel):
    summary_markdown: str
    cited_doc_pages: list[int] = Field(default_factory=list)
    cited_regulation_ids: list[str] = Field(default_factory=list)


def generate_explanation(
    parsed_doc: dict[str, Any],
    regulation_context: list[dict[str, Any]],
    risk_result: dict[str, Any] | None = None,
    regeneration_instruction: str | None = None,
) -> ExplanationOutput:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = _get_setting("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is required to generate an explanation. "
            "Set it in Streamlit Cloud app Secrets or the local .env file."
        )

    prompt_data = {
        "document_filename": parsed_doc.get("filename", "unknown"),
        "document_pages": parsed_doc.get("pages", {}),
        "risk_result": risk_result,
        "regulatory_evidence": [
            {
                "regulation_id": item["metadata"].get("para_id"),
                "section_path": item["metadata"].get("section_path"),
                "text": item["text"],
            }
            for item in regulation_context
        ],
        "regeneration_instruction": regeneration_instruction,
    }
    prompt = (
        "Explain the document and its relevant regulatory evidence using only "
        "the supplied data. Return concise, factual Markdown. Cite document pages "
        "using their supplied page numbers and regulations only with supplied "
        "regulation IDs. Do not invent facts, rules, or citations. If an issue "
        "cannot be determined from the evidence, say so. Return a JSON object "
        "matching this schema, without Markdown fences:\n"
        f"{json.dumps(ExplanationOutput.model_json_schema())}\n\n"
        f"Evidence JSON:\n{json.dumps(prompt_data, ensure_ascii=False, default=str)}"
    )
    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=45.0,
        max_retries=0,
    )
    try:
        response = client.chat.completions.create(
            model=_get_setting(
                "OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"
            ),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a careful financial-document compliance explainer. "
                        "Use only the supplied evidence and return valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            extra_body={"reasoning": {"enabled": True}},
            temperature=0.1,
            max_completion_tokens=1024,
        )
    except AuthenticationError as error:
        raise RuntimeError(
            "OpenRouter rejected the API key (401). Create a replacement key in "
            "your OpenRouter account, update OPENROUTER_API_KEY in the project's "
            ".env file or process environment, and restart the app. Do not share "
            "the key."
        ) from error

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenRouter returned an empty explanation.")
    return ExplanationOutput.model_validate_json(content)
