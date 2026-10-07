from __future__ import annotations

import os

from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    model = os.getenv("GEMINI_MODEL")
    if not api_key:
        print("FAIL: GEMINI_API_KEY is not set")
        return 1
    if not model:
        print("FAIL: GEMINI_MODEL is not set")
        return 1

    try:
        from google import genai

        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents="Reply with exactly: GEMINI_DIAGNOSTIC_OK",
            config={"temperature": 0},
        )
        text = (response.text or "").strip()
        if not text:
            print(f"FAIL: model {model} returned an empty response")
            return 1
        print(f"PASS: Gemini model {model} is reachable and returned a response")
        print(f"Response preview: {text[:120]}")
        return 0
    except Exception as exc:
        print(f"FAIL: Gemini model {model} request failed: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
