import random
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.cards.models import Card, Theme
from apps.core.models import Player, PlayerWeeklyTheme

from .base import BaseUseCase
from .draw_themes import week_start

MAX_REROLLS_PER_WEEK = 2
RECENT_WEEKS_EXCLUDED = 4  # inclui a semana atual


def comfort_theme_slugs(player):
    """Temas principais (EDHREC) dos comandantes de todos os decks do jogador."""
    slugs = set()
    for theme_slugs in Card.objects.filter(
        decks_as_commander__player=player
    ).values_list("edhrec_theme_slugs", flat=True):
        slugs.update(theme_slugs or [])
    return slugs


def eligible_weekly_themes(player, week):
    """
    Temas que podem sair para o jogador na semana `week` (date da segunda).
    Regra completa: fora da zona de conforto e fora dos temas que ele
    recebeu nas últimas 4 semanas. Se não sobrar nada, relaxa primeiro as
    4 semanas (mantendo "não repetir nesta semana") e depois a zona de
    conforto. Pode devolver vazio.
    """
    comfort = comfort_theme_slugs(player)
    mine = PlayerWeeklyTheme.objects.filter(player=player)
    this_week = mine.filter(week_start=week).values("theme_id")
    recent = mine.filter(
        week_start__gte=week - timedelta(weeks=RECENT_WEEKS_EXCLUDED - 1)
    ).values("theme_id")

    candidates = [
        Theme.objects.exclude(slug__in=comfort).exclude(id__in=recent),
        Theme.objects.exclude(slug__in=comfort).exclude(id__in=this_week),
        Theme.objects.exclude(id__in=this_week),
    ]
    for queryset in candidates:
        if queryset.exists():
            return queryset
    return candidates[-1]


def _week(now):
    return week_start(now or timezone.now()).date()


def _rows(player, week):
    return PlayerWeeklyTheme.objects.filter(player=player, week_start=week)


def _result(player, week):
    rows = _rows(player, week)
    current = rows.select_related("theme").first()
    if current is None:
        return None
    return {
        "theme": current.theme,
        "rerolls_left": max(0, MAX_REROLLS_PER_WEEK - (rows.count() - 1)),
    }


def _draw(player, week):
    ids = list(eligible_weekly_themes(player, week).values_list("id", flat=True))
    if not ids:
        return False
    PlayerWeeklyTheme.objects.create(player=player, theme_id=random.choice(ids), week_start=week)
    return True


def _lock(player):
    # Trava a linha do jogador: duas requisições simultâneas não criam duas
    # linhas (e não gastam uma troca sem querer).
    Player.objects.select_for_update().filter(pk=player.pk).first()


class EnsureWeeklyThemeUseCase(BaseUseCase):
    """Garante o Tema da Semana do jogador: sorteia na primeira visita da semana."""

    def perform_request(self, player, now=None):
        week = _week(now)
        with transaction.atomic():
            _lock(player)
            if not _rows(player, week).exists():
                _draw(player, week)
            return _result(player, week)


class RerollWeeklyThemeUseCase(BaseUseCase):
    """
    Troca o Tema da Semana (até 2 vezes por semana), nunca voltando a um tema
    já sorteado para o jogador nesta semana. Sem linha na semana, vale como o
    primeiro sorteio. Sem tema possível, devolve None sem gastar troca.
    """

    def perform_request(self, player, now=None):
        week = _week(now)
        with transaction.atomic():
            _lock(player)
            rows = _rows(player, week).count()
            if rows == 0:
                _draw(player, week)
                return _result(player, week)
            if rows - 1 >= MAX_REROLLS_PER_WEEK:
                raise ValidationError(
                    f"Você já usou as {MAX_REROLLS_PER_WEEK} trocas desta semana."
                )
            if not _draw(player, week):
                return None
            return _result(player, week)
