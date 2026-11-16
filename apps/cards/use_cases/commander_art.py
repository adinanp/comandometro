import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from apps.core.use_cases.base import BaseUseCase

from .card_image import SCRYFALL_HEADERS

logger = logging.getLogger(__name__)

SCRYFALL_NAMED_URL = "https://api.scryfall.com/cards/named?{query}"


class ResolveCommanderArtUseCase(BaseUseCase):
    """
    Devolve a URL do recorte de arte (`art_crop`) de um comandante, buscando
    no Scryfall por nome exato. Para pares de partner ("A // B") usa a
    primeira carta. Qualquer falha devolve None — quem chama segue sem arte.
    """

    def perform_request(self, commander_name):
        name = commander_name.split(" // ")[0].strip()
        url = SCRYFALL_NAMED_URL.format(query=urllib.parse.urlencode({"exact": name}))
        req = urllib.request.Request(url, headers=SCRYFALL_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                card = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError):
            logger.warning("Não foi possível buscar a arte de %s no Scryfall", name)
            return None

        image_uris = card.get("image_uris")
        if not image_uris and card.get("card_faces"):
            image_uris = card["card_faces"][0].get("image_uris")
        return (image_uris or {}).get("art_crop")
