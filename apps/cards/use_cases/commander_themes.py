import logging
import time

from django.utils import timezone

from apps.cards.edhrec import EdhrecThemeClient
from apps.core.use_cases.base import BaseUseCase

logger = logging.getLogger(__name__)

COMFORT_THEMES_PER_COMMANDER = 5


class EnsureCommanderThemesUseCase(BaseUseCase):
    """
    Guarda em cada carta os temas principais dela como comandante no EDHREC
    (usados para a zona de conforto do Tema da Semana). Pula cartas já
    sincronizadas, a menos que `refresh`. Falha numa carta é logada e não
    impede as outras; a carta fica sem `edhrec_themes_synced_at` para ser
    tentada de novo. Devolve quantas cartas foram atualizadas.
    """

    def perform_request(self, cards, client=None, refresh=False, delay=0):
        client = client or EdhrecThemeClient()
        updated = fetched = 0
        for card in cards:
            if card.edhrec_themes_synced_at and not refresh:
                continue
            if fetched and delay:
                time.sleep(delay)  # mantém o ritmo abaixo de ~5 req/s
            fetched += 1
            try:
                slugs = client.commander_theme_slugs(
                    card.name, limit=COMFORT_THEMES_PER_COMMANDER
                )
            except Exception:  # um comandante com problema não para os outros
                logger.warning("Falha ao buscar temas de %s", card.name, exc_info=True)
                continue
            card.edhrec_theme_slugs = slugs
            card.edhrec_themes_synced_at = timezone.now()
            card.save(update_fields=["edhrec_theme_slugs", "edhrec_themes_synced_at"])
            updated += 1
        return updated


DECK_SAVE_TIMEOUT_S = 3


def ensure_deck_commander_themes(deck):
    """
    Chamado pelas views depois de salvar um deck: busca no EDHREC os temas
    dos comandantes que ainda não têm dados, com timeout curto. Nunca
    propaga erro — salvar um deck não pode falhar por causa do EDHREC.
    """
    try:
        EnsureCommanderThemesUseCase().execute(
            deck.commanders.all(), client=EdhrecThemeClient(timeout=DECK_SAVE_TIMEOUT_S)
        )
    except Exception:
        logger.warning("Falha ao buscar temas dos comandantes do deck %s", deck.pk, exc_info=True)
