import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENROUTER_API_KEY is missing. Add it to the ignored project .env "
            "file; do not paste it into chat."
        )

    client = OpenAI(
        api_key=api_key,
        base_url="https://openrouter.ai/api/v1",
        timeout=45.0,
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=os.environ.get(
            "OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"
        ),
        messages=[
            {
                "role": "user",
                "content": "Reply with exactly: OPENROUTER_OK",
            }
        ],
        extra_body={"reasoning": {"enabled": True}},
        max_completion_tokens=128,
        temperature=0,
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("OpenRouter returned an empty smoke-check response.")
    print("OpenRouter LLM check:", content)


if __name__ == "__main__":
    main()
