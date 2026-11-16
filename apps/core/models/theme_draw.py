from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.cards.models import Theme
from .player import Player


class ThemeDraw(models.Model):
    """Um sorteio de temas: 4 jogadores do pod, um tema distinto para cada."""

    pod = models.ForeignKey(
        "pods.Pod", on_delete=models.CASCADE, related_name="theme_draws"
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="theme_draws",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Sorteio de temas #{self.pk} ({self.pod})"


class ThemeDrawSeat(models.Model):
    """Jogador + tema sorteado. O pod vem de `draw.pod` (sem campo próprio)."""

    draw = models.ForeignKey(ThemeDraw, on_delete=models.CASCADE, related_name="seats")
    player = models.ForeignKey(
        Player, on_delete=models.CASCADE, related_name="theme_draw_seats"
    )
    theme = models.ForeignKey(
        Theme, on_delete=models.PROTECT, related_name="draw_seats"
    )
    position = models.PositiveSmallIntegerField()

    class Meta:
        ordering = ["position"]
        unique_together = [("draw", "player"), ("draw", "theme")]

    def __str__(self):
        return f"{self.player} — {self.theme}"

    def clean(self):
        super().clean()
        if self.player_id and self.draw_id and self.player.pod_id != self.draw.pod_id:
            raise ValidationError("O jogador precisa ser do mesmo pod do sorteio.")
