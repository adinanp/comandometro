import logging
import time

from django.utils import timezone

from apps.cards.edhrec import EdhrecError, EdhrecThemeClient
from apps.cards.models import Theme
from apps.core.use_cases.base import BaseUseCase

from .commander_art import ResolveCommanderArtUseCase

logger = logging.getLogger(__name__)

TOP_COMMANDERS_STORED = 10


class SyncEdhrecThemesUseCase(BaseUseCase):
    """
    Atualiza o catálogo de temas a partir do EDHREC: upsert da lista
    completa e, para cada tema, os top comandantes e a arte do nº 1.
    Falha num tema é registrada e o resto segue. Temas que somem do EDHREC
    não são apagados (sorteios antigos apontam para eles). Não mexe em
    `summary` — resumos nascem no primeiro sorteio.
    """

    def perform_request(self, client=None, only=None, delay=0.2):
        client = client or EdhrecThemeClient()
        listings = client.list_themes()

        for listing in listings:
            Theme.objects.update_or_create(
                slug=listing.slug,
                defaults={
                    "name": listing.name,
                    "num_decks": listing.num_decks,
                    "popularity_rank": listing.popularity_rank,
                },
            )

        slugs = [l.slug for l in listings if only is None or l.slug == only]
        ok, failed = 0, []
        for index, slug in enumerate(slugs):
            if index and delay:
                time.sleep(delay)  # mantém o ritmo abaixo de ~5 req/s
            try:
                commanders = client.top_commanders(slug, limit=TOP_COMMANDERS_STORED)
            except EdhrecError:
                logger.warning("Falha ao sincronizar o tema %s", slug)
                failed.append(slug)
                continue
            self._save_details(Theme.objects.get(slug=slug), commanders)
            ok += 1

        return {"themes": len(listings), "ok": ok, "failed": failed}

    def _save_details(self, theme, commanders):
        previous_top = theme.top_commander_names(limit=1)
        theme.top_commanders = commanders
        new_top = theme.top_commander_names(limit=1)
        if not new_top:
            theme.art_crop_url = ""
        elif new_top != previous_top or not theme.art_crop_url:
            theme.art_crop_url = ResolveCommanderArtUseCase().execute(new_top[0]) or ""
        theme.edhrec_synced_at = timezone.now()
        theme.save(update_fields=["top_commanders", "art_crop_url", "edhrec_synced_at"])
