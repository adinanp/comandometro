import json
import logging
import urllib.error
import urllib.request

from apps.shared.use_cases import BaseUseCase

logger = logging.getLogger(__name__)

SCRYFALL_CARD_URL = "https://api.scryfall.com/cards/{scryfall_id}"


class EnsureCardImageUseCase(BaseUseCase):
    """
    Garante que um Card tenha `image_url` preenchido, buscando na API do
    Scryfall sob demanda e cacheando o resultado no próprio registro.
    Nunca derruba a tela que a chamou: falha de rede, carta sem
    scryfall_id, ou carta sem imagem simplesmente retornam None.
    """

    def perform_request(self, card):
        if card.image_url:
            return card.image_url

        if not card.scryfall_id:
            return None

        url = SCRYFALL_CARD_URL.format(scryfall_id=card.scryfall_id)
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError):
            logger.warning(
                "Não foi possível buscar imagem no Scryfall para %s", card.name
            )
            return None

        image_uris = payload.get("image_uris")
        if not image_uris and payload.get("card_faces"):
            image_uris = payload["card_faces"][0].get("image_uris")

        if not image_uris:
            return None

        image_url = image_uris.get("normal")
        if image_url:
            card.image_url = image_url
            card.save(update_fields=["image_url"])

        return image_url
