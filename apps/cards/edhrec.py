"""
Cliente da API JSON não oficial do EDHREC (json.edhrec.com), isolado aqui
para que mudanças de formato fiquem num lugar só. Usado apenas pelo comando
`sync_edhrec_themes` — nada do app consulta o EDHREC durante o uso normal.
"""

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

EDHREC_BASE_URL = "https://json.edhrec.com/pages"
EDHREC_HEADERS = {"User-Agent": "Comandometro/1.0", "Accept": "application/json"}
TAGS_PREFIX = "/tags/"


class EdhrecError(Exception):
    pass


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
                return [
                    {"name": c["name"], "num_decks": int(c.get("num_decks") or 0)}
                    for c in cardlist.get("cardviews", [])[:limit]
                ]
        return []

    def _get_json(self, url):
        req = urllib.request.Request(url, headers=EDHREC_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise EdhrecError(f"Falha ao buscar {url}: {exc}") from exc
