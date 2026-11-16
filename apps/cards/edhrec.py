"""
Cliente da API JSON não oficial do EDHREC (json.edhrec.com), isolado aqui
para que mudanças de formato fiquem num lugar só. Usado pelo comando
`sync_edhrec_themes` e, para os temas de comandantes novos, ao salvar um deck.
Dashboard e sorteios nunca consultam o EDHREC.
"""

import http.client
import json
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass

EDHREC_BASE_URL = "https://json.edhrec.com/pages"
EDHREC_HEADERS = {"User-Agent": "Comandometro/1.0", "Accept": "application/json"}
TAGS_PREFIX = "/tags/"


# Páginas inexistentes: o EDHREC serve o JSON de um bucket S3, que responde
# 403 com <Code>AccessDenied</Code>. Um 403 com outro corpo (WAF, rate limit,
# IP bloqueado) é erro de verdade e não pode virar "comandante sem temas".
S3_MISSING_KEY_MARKER = b"<Code>AccessDenied</Code>"


class EdhrecError(Exception):
    pass


class EdhrecNotFound(EdhrecError):
    pass


def edhrec_commander_slug(name):
    """Slug da página do comandante: "Atraxa, Praetors' Voice" → atraxa-praetors-voice."""
    name = name.split(" // ")[0]
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    name = re.sub(r"['’,]", "", name.lower())
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


@dataclass(frozen=True)
class ThemeListing:
    slug: str
    name: str
    num_decks: int
    popularity_rank: int


def _cardlists(payload):
    return payload.get("container", {}).get("json_dict", {}).get("cardlists", [])


class EdhrecThemeClient:
    def __init__(self, timeout=10):
        self.timeout = timeout

    def list_themes(self):
        return self.parse_theme_list(self._get_json(f"{EDHREC_BASE_URL}/tags.json"))

    def top_commanders(self, slug, limit=10):
        payload = self._get_json(f"{EDHREC_BASE_URL}/tags/{slug}.json")
        return self.parse_top_commanders(payload, limit)

    @staticmethod
    def parse_theme_list(payload):
        lists = _cardlists(payload)
        if not lists:
            raise EdhrecError("Catálogo de temas do EDHREC sem cardlists")
        themes = []
        for item in lists[0].get("cardviews", []):
            url = item.get("url") or ""
            if not url.startswith(TAGS_PREFIX):
                continue
            themes.append(
                ThemeListing(
                    slug=url[len(TAGS_PREFIX):],
                    name=item.get("name", ""),
                    num_decks=int(item.get("num_decks") or 0),
                    popularity_rank=len(themes) + 1,
                )
            )
        return themes

    @staticmethod
    def parse_top_commanders(payload, limit):
        for cardlist in _cardlists(payload):
            if cardlist.get("tag") == "topcommanders":
                commanders = [
                    {"name": c["name"], "num_decks": int(c.get("num_decks") or 0)}
                    for c in cardlist.get("cardviews", [])
                    if c.get("name")
                ]
                return commanders[:limit]
        return []

    def commander_theme_slugs(self, card_name, limit=5):
        url = f"{EDHREC_BASE_URL}/commanders/{edhrec_commander_slug(card_name)}.json"
        try:
            payload = self._get_json(url)
        except EdhrecNotFound:
            return []
        return self.parse_commander_theme_slugs(payload, limit)

    @staticmethod
    def parse_commander_theme_slugs(payload, limit):
        panels = payload.get("panels") or {}
        taglinks = panels.get("taglinks") if isinstance(panels, dict) else None
        return [t["slug"] for t in (taglinks or []) if t.get("slug")][:limit]

    def _get_json(self, url):
        req = urllib.request.Request(url, headers=EDHREC_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if self._is_missing_page(exc):
                raise EdhrecNotFound(url) from exc
            raise EdhrecError(f"Falha ao buscar {url}: {exc}") from exc
        # OSError cobre URLError/timeout/reset; HTTPException cobre corpo truncado.
        except (OSError, http.client.HTTPException, ValueError) as exc:
            raise EdhrecError(f"Falha ao buscar {url}: {exc}") from exc

    @staticmethod
    def _is_missing_page(exc):
        if exc.code == 404:
            return True
        if exc.code != 403:
            return False
        try:
            return S3_MISSING_KEY_MARKER in (exc.read() or b"")
        except Exception:
            return False
