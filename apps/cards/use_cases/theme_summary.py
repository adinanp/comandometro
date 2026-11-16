import logging
import re

from django.conf import settings
from django.utils import timezone

from apps.cards.llm import LlmError, generate_text
from apps.core.use_cases.base import BaseUseCase

logger = logging.getLogger(__name__)

SUMMARY_MAX_CHARS = 120
_QUOTES = "\"'“”‘’«»"
_PREFIX = re.compile(r"^(resumo|summary)\s*:\s*", re.IGNORECASE)
_MARKDOWN = re.compile(r"[*_`#]+")


def build_summary_prompt(theme):
    commanders = ", ".join(theme.top_commander_names()) or "(sem dados)"
    return (
        f"Tema de Commander (EDH) no EDHREC: {theme.name}.\n"
        f"Comandantes mais populares do tema: {commanders}.\n\n"
        "Escreva em português do Brasil UMA frase explicando como esse tema "
        "joga e como costuma vencer, para um jogador de Magic que não conhece "
        f"o tema. No máximo {SUMMARY_MAX_CHARS} caracteres. Mantenha nomes de "
        "cartas em inglês e cite apenas cartas da lista acima, se citar. "
        "Responda só com a frase, sem aspas e sem prefixo."
    )


def clean_summary(raw, max_chars=SUMMARY_MAX_CHARS):
    # Só o primeiro parágrafo: depois de uma linha em branco costuma vir
    # nota/explicação. Quebras simples dentro do parágrafo viram espaço.
    paragraphs = [p for p in re.split(r"\n\s*\n", raw) if p.strip()]
    first = paragraphs[0] if paragraphs else ""
    text = _MARKDOWN.sub("", " ".join(first.split()))
    text = text.strip(_QUOTES + " ")
    text = _PREFIX.sub("", text).strip(_QUOTES + " ")
    if len(text) <= max_chars:
        return text
    cut = text[: max_chars - 1]
    if " " in cut:
        cut = cut[: cut.rfind(" ")]
    return cut.rstrip(" ,;:.-") + "…"


class EnsureThemeSummaryUseCase(BaseUseCase):
    """
    Garante o resumo pt-BR de um tema: devolve o salvo ou gera uma vez via
    LLM e salva. Sem GEMINI_API_KEY, ou se a LLM falhar, devolve None sem
    salvar (a próxima vez que o tema aparecer tenta de novo).
    """

    def perform_request(self, theme):
        if theme.summary:
            return theme.summary
        if not settings.GEMINI_API_KEY:
            return None

        try:
            raw = generate_text(
                build_summary_prompt(theme),
                model=settings.GEMINI_MODEL,
                api_key=settings.GEMINI_API_KEY,
            )
        except LlmError:
            logger.warning("Falha ao gerar resumo do tema %s", theme.slug)
            return None

        summary = clean_summary(raw)
        if not summary:
            return None

        theme.summary = summary
        theme.summary_model = settings.GEMINI_MODEL
        theme.summary_generated_at = timezone.now()
        theme.save(update_fields=["summary", "summary_model", "summary_generated_at"])
        return summary
