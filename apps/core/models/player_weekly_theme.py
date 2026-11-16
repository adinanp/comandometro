from django.db import models

from apps.cards.models import Theme
from .player import Player


class PlayerWeeklyTheme(models.Model):
    """
    Um tema sorteado para o jogador numa semana (o "Tema da Semana"). Cada
    troca cria uma linha nova: o tema atual é a linha mais recente da
    semana, e as trocas usadas são as linhas da semana menos 1. O pod vem
    de `player.pod`.
    """

    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="weekly_themes"
    )
    theme = models.ForeignKey(
        Theme, on_delete=models.PROTECT, related_name="weekly_picks"
    )
    week_start = models.DateField(help_text="Segunda-feira da semana (America/Sao_Paulo)")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["player", "week_start"])]
        unique_together = [("player", "week_start", "theme")]

    def __str__(self):
        return f"{self.player} — {self.theme} ({self.week_start:%d/%m})"
