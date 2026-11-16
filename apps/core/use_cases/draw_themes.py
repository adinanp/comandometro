import random
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.cards.models import Theme
from apps.core.models import ThemeDraw, ThemeDrawSeat
from apps.pods.models import Pod

from .base import BaseUseCase

PLAYERS_PER_DRAW = 4
# A regra "não repetir na mesma semana" segue o calendário do grupo (Brasil),
# não o TIME_ZONE do projeto (UTC) — senão a semana viraria domingo 21h.
WEEK_TIMEZONE = ZoneInfo("America/Sao_Paulo")


def week_start(now):
    """Segunda-feira 00:00 (America/Sao_Paulo) da semana de `now`."""
    local = now.astimezone(WEEK_TIMEZONE)
    monday = local.date() - timedelta(days=local.weekday())
    return datetime.combine(monday, time.min, tzinfo=WEEK_TIMEZONE)


class DrawThemesUseCase(BaseUseCase):
    """
    Sorteia um tema distinto para cada um dos 4 jogadores, evitando temas já
    sorteados no mesmo pod nesta semana. Se sobrarem menos de 4 elegíveis,
    completa com os demais em vez de falhar.
    """

    @staticmethod
    def eligible_themes(pod, now=None):
        used = ThemeDrawSeat.objects.filter(
            draw__pod=pod, draw__created_at__gte=week_start(now or timezone.now())
        ).values("theme_id")
        return Theme.objects.exclude(id__in=used)

    def perform_request(self, pod, players, created_by=None):
        players = list(players)
        if len(players) != PLAYERS_PER_DRAW or len(set(players)) != PLAYERS_PER_DRAW:
            raise ValidationError(f"Escolha exatamente {PLAYERS_PER_DRAW} jogadores diferentes.")
        if any(player.pod_id != pod.id for player in players):
            raise ValidationError("Todos os jogadores precisam ser deste pod.")

        with transaction.atomic():
            # Trava o pod: dois sorteios simultâneos esperam um pelo outro e o
            # segundo já enxerga os temas que o primeiro acabou de usar.
            Pod.objects.select_for_update().filter(pk=pod.pk).first()

            all_ids = list(Theme.objects.values_list("id", flat=True))
            if len(all_ids) < PLAYERS_PER_DRAW:
                raise ValidationError("O catálogo de temas ainda não foi carregado.")

            eligible = list(self.eligible_themes(pod).values_list("id", flat=True))
            if len(eligible) >= PLAYERS_PER_DRAW:
                theme_ids = random.sample(eligible, PLAYERS_PER_DRAW)
            else:
                eligible_set = set(eligible)
                rest = [i for i in all_ids if i not in eligible_set]
                theme_ids = eligible + random.sample(rest, PLAYERS_PER_DRAW - len(eligible))

            draw = ThemeDraw.objects.create(pod=pod, created_by=created_by)
            for position, (player, theme_id) in enumerate(zip(players, theme_ids)):
                seat = ThemeDrawSeat(
                    draw=draw, player=player, theme_id=theme_id, position=position
                )
                seat.full_clean()
                seat.save()
        return draw
