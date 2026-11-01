import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GROQ_API_KEY is missing. Add it to the ignored project .env file; "
            "do not paste it into chat."
        )

    client = OpenAI(
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        timeout=45.0,
        max_retries=0,
    )
    response = client.chat.completions.create(
        model=os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b"),
        messages=[
            {
                "role": "user",
                "content": "Reply with exactly: GROQ_OK",
            }
        ],
        max_completion_tokens=128,
        temperature=0,
    )

    content = response.choices[0].message.content
    if not content:
        raise RuntimeError("Groq returned an empty smoke-check response.")
    print("Groq LLM check:", content)


if __name__ == "__main__":
    main()
