"""
Fronteira com o provedor de LLM (Gemini via google-genai). O resto do app só
conhece `generate_text` e `LlmError`, então trocar de provedor mexe só aqui.
"""

from google import genai
from google.genai import types


class LlmError(Exception):
    pass


def generate_text(prompt, *, model, api_key, timeout_s=8.0):
    try:
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(timeout=int(timeout_s * 1000)),
        )
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text or ""
    except Exception as exc:  # SDK levanta tipos variados (rede, cota, 4xx/5xx)
        raise LlmError(str(exc)) from exc
