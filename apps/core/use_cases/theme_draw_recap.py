import io
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor, wait
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from .base import BaseUseCase

logger = logging.getLogger(__name__)

FONTS_DIR = Path(__file__).resolve().parent.parent / "static" / "core" / "fonts"
ART_HEADERS = {"User-Agent": "Comandometro/1.0"}
ART_TIMEOUT_S = 8
ART_DEADLINE_S = 10  # prazo total dos downloads (gunicorn mata o worker em 30 s)

WIDTH, HEIGHT = 1080, 1350
MARGIN = 45
ROWS_TOP = 180
ROW_HEIGHT = 260
ROW_GAP = 15
ART_WIDTH = 275
TEXT_PADDING = 30

BACKGROUND = "#141210"
ROW_BACKGROUND = "#24201d"
ART_PLACEHOLDER = "#3a3430"
ACCENT = "#e24c2c"
THEME_COLOR = "#f0c9a0"
MUTED = "#aaaaaa"
COMMANDER_COLOR = "#bbbbbb"
SUMMARY_COLOR = "#e8e2da"
WHITE = "#ffffff"
ELLIPSIS = "…"


@lru_cache(maxsize=None)
def load_font(kind, size):
    """kind: "display" (Archivo Black) ou "body" (Inter Regular)."""
    if kind == "display":
        return ImageFont.truetype(str(FONTS_DIR / "ArchivoBlack-Regular.ttf"), size)
    font = ImageFont.truetype(str(FONTS_DIR / "Inter-Variable.ttf"), size)
    font.set_variation_by_name("Regular")
    return font


def _ellipsize(canvas, text, font, max_width):
    text = text.rstrip()
    while text and canvas.textlength(text + ELLIPSIS, font=font) > max_width:
        text = text[:-1].rstrip()
    return text + ELLIPSIS


def fit_text(canvas, text, font, max_width, max_lines):
    """
    Quebra `text` em até `max_lines` linhas que cabem em `max_width` (medido
    com a fonte real). O que não couber vira "…" no fim da última linha.
    """
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if current and canvas.textlength(candidate, font=font) > max_width:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)

    overflow = len(lines) > max_lines
    lines = lines[:max_lines]
    for index, line in enumerate(lines):
        is_last = index == len(lines) - 1
        if canvas.textlength(line, font=font) > max_width or (is_last and overflow):
            lines[index] = _ellipsize(canvas, line, font, max_width)
    return lines


def fit_line(canvas, text, font, max_width):
    """Uma linha só, cortada com "…" se precisar; "" se não houver texto."""
    lines = fit_text(canvas, text, font, max_width, 1)
    return lines[0] if lines else ""


def _download_art(url):
    req = urllib.request.Request(url, headers=ART_HEADERS)
    with urllib.request.urlopen(req, timeout=ART_TIMEOUT_S) as response:
        return Image.open(io.BytesIO(response.read())).convert("RGB")


def _download_all(urls):
    """Baixa as artes em paralelo; o que falhar ou estourar o prazo vira None."""
    results = {url: None for url in urls}
    if not urls:
        return results
    executor = ThreadPoolExecutor(max_workers=len(urls))
    futures = {executor.submit(_download_art, url): url for url in urls}
    done, _ = wait(futures, timeout=ART_DEADLINE_S)
    for future in done:
        try:
            results[futures[future]] = future.result()
        except Exception:  # arte é opcional: qualquer falha vira o bloco neutro
            logger.warning("Não foi possível baixar a arte %s", futures[future], exc_info=True)
    executor.shutdown(wait=False, cancel_futures=True)
    return results


class ThemeDrawRecapUseCase(BaseUseCase):
    """
    Desenha o recap do sorteio (PNG 1080x1350, layout "A · Lista"): selo,
    nome do pod e uma linha por jogador com arte do comandante nº 1, tema,
    nº de decks, comandante e resumo. Usa só resumos já salvos — nunca chama
    a LLM — para a requisição não estourar o timeout.
    """

    def perform_request(self, draw):
        seats = list(draw.seats.select_related("player", "theme"))
        arts = _download_all(
            list({s.theme.art_crop_url for s in seats if s.theme.art_crop_url})
        )

        image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
        canvas = ImageDraw.Draw(image)
        self._draw_header(canvas, draw.pod.name)
        for index, seat in enumerate(seats):
            top = ROWS_TOP + index * (ROW_HEIGHT + ROW_GAP)
            self._draw_row(image, canvas, top, seat, arts.get(seat.theme.art_crop_url))
        self._draw_footer(canvas)

        buffer = io.BytesIO()
        image.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()

    def _draw_header(self, canvas, pod_name):
        badge_font = load_font("display", 25)
        label = "SORTEIO DE TEMAS"
        left, top, right, bottom = canvas.textbbox((0, 0), label, font=badge_font)
        pad_x, pad_y = 20, 12
        canvas.rectangle(
            (MARGIN, 45, MARGIN + (right - left) + 2 * pad_x, 45 + (bottom - top) + 2 * pad_y),
            fill=ACCENT,
        )
        canvas.text((MARGIN + pad_x - left, 45 + pad_y - top), label, font=badge_font, fill=WHITE)

        pod_font = load_font("display", 22)
        max_width = WIDTH - 2 * MARGIN
        pod_line = fit_line(canvas, pod_name.upper(), pod_font, max_width)
        canvas.text((MARGIN, 45 + (bottom - top) + 2 * pad_y + 20), pod_line, font=pod_font, fill=ACCENT)

    def _draw_row(self, image, canvas, top, seat, art):
        left, right = MARGIN, WIDTH - MARGIN
        canvas.rectangle((left, top, right, top + ROW_HEIGHT), fill=ROW_BACKGROUND)
        if art is not None:
            image.paste(ImageOps.fit(art, (ART_WIDTH, ROW_HEIGHT)), (left, top))
        else:
            canvas.rectangle((left, top, left + ART_WIDTH, top + ROW_HEIGHT), fill=ART_PLACEHOLDER)

        theme = seat.theme
        x = left + ART_WIDTH + TEXT_PADDING
        text_width = right - TEXT_PADDING - x

        decks_font = load_font("body", 20)
        decks = theme.display_num_decks()
        decks_width = canvas.textlength(decks, font=decks_font)
        canvas.text((right - TEXT_PADDING, top + 30), decks, font=decks_font, fill=MUTED, anchor="ra")

        player_font = load_font("display", 32)
        player = fit_line(canvas, str(seat.player), player_font, text_width - decks_width - 20)
        canvas.text((x, top + 22), player, font=player_font, fill=WHITE)

        theme_font = load_font("display", 25)
        theme_line = fit_line(canvas, theme.name.upper(), theme_font, text_width)
        canvas.text((x, top + 72), theme_line, font=theme_font, fill=THEME_COLOR)

        y = top + 115
        commanders = theme.top_commander_names(limit=1)
        if commanders and commanders[0]:
            commander_font = load_font("body", 19)
            line = fit_line(canvas, f"Top comandante: {commanders[0]}", commander_font, text_width)
            canvas.text((x, y), line, font=commander_font, fill=COMMANDER_COLOR)
            y += 38

        if theme.summary:
            summary_font = load_font("body", 20)
            for line in fit_text(canvas, theme.summary, summary_font, text_width, 2):
                canvas.text((x, y), line, font=summary_font, fill=SUMMARY_COLOR)
                y += 28

    def _draw_footer(self, canvas):
        y = HEIGHT - 45
        canvas.text((MARGIN, y), "COMANDÔMETRO", font=load_font("display", 25), fill=WHITE, anchor="ls")
        canvas.text(
            (WIDTH - MARGIN, y), "sorteio de temas", font=load_font("body", 20), fill=MUTED, anchor="rs"
        )
