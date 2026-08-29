import json
import logging
import urllib.error
import urllib.request

from apps.core.use_cases.base import BaseUseCase

logger = logging.getLogger(__name__)

SCRYFALL_SEARCH_URL = (
    "https://api.scryfall.com/cards/search?q=oracleid:{oracle_id}&unique=prints"
)
SCRYFALL_HEADERS = {"User-Agent": "Comandometro/1.0", "Accept": "application/json"}


class EnsureCardImageUseCase(BaseUseCase):
    """
    Garante que um Card tenha `image_url` preenchido, buscando na API do
    Scryfall sob demanda (por Oracle ID, já que o MTGJSON só fornece esse
    identificador, compartilhado entre reimpressões) e cacheando o
    resultado no próprio registro. Nunca derruba a tela que a chamou:
    falha de rede, carta sem scryfall_oracle_id, ou carta sem imagem
    simplesmente retornam None.
    """

    def perform_request(self, card):
        if card.image_url:
            return card.image_url

        if not card.scryfall_oracle_id:
            return None

        url = SCRYFALL_SEARCH_URL.format(oracle_id=card.scryfall_oracle_id)
        req = urllib.request.Request(url, headers=SCRYFALL_HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError):
            logger.warning(
                "Não foi possível buscar imagem no Scryfall para %s", card.name
            )
            return None

        results = payload.get("data") or []
        if not results:
            return None

        card_data = results[0]
        image_uris = card_data.get("image_uris")
        if not image_uris and card_data.get("card_faces"):
            image_uris = card_data["card_faces"][0].get("image_uris")

        if not image_uris:
            return None

        image_url = image_uris.get("normal")
        if image_url:
            card.image_url = image_url
            card.save(update_fields=["image_url"])

        return image_url
