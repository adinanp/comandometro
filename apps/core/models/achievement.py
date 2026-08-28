from django.db import models


class Achievement(models.Model):
    title = models.CharField(
        max_length=150,
        help_text="Nome da conquista ou recorde (ex: 'Maior Torment of Hailfire', 'Matar com Sign in Blood')"
    )
    detail = models.CharField(
        max_length=255,
        blank=True,
        help_text="Detalhes do feito (ex: 'X=34', 'Adinan matou Alex')"
    )
    player = models.ForeignKey(
        'core.Player',
        on_delete=models.CASCADE,
        related_name='achievements',
        help_text="Jogador que alcançou a conquista"
    )
    game = models.ForeignKey(
        'core.Game',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='achievements',
        help_text="Partida em que o feito ocorreu (opcional)"
    )
    date = models.DateField(
        null=True,
        blank=True,
        help_text="Data do feito (preenchida automaticamente se a partida for vinculada)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def clean(self):
        super().clean()
        # Herda a data da partida se uma for selecionada e a data estiver em branco
        if self.game and self.game.date and not self.date:
            self.date = self.game.date

    def __str__(self):
        player_name = self.player.nickname or self.player.name
        detail_str = f" ({self.detail})" if self.detail else ""
        return f"{self.title}{detail_str} - {player_name}"
