"""
Fronteira com o provedor de LLM (Gemini via google-genai). O resto do app só
conhece `generate_text` e `LlmError`, então trocar de provedor mexe só aqui.
"""

from google import genai
from google.genai import types


class LlmError(Exception):
    pass


# A API do Gemini recusa (400 INVALID_ARGUMENT) prazos abaixo de 10 s.
MIN_TIMEOUT_S = 10.0


def generate_text(prompt, *, model, api_key, timeout_s=MIN_TIMEOUT_S):
    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=int(max(timeout_s, MIN_TIMEOUT_S) * 1000)
            ),
        )
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text or ""
    except Exception as exc:  # SDK levanta tipos variados (rede, cota, 4xx/5xx)
        raise LlmError(str(exc)) from exc
