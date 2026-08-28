from django.db import models
from .game import Game
from .player import Player
from .deck import Deck
from .card import Card


class GameParticipant(models.Model):
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name='participants'
    )
    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name='match_performances'
    )
    deck = models.ForeignKey(
        Deck,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='match_performances'
    )
    placement = models.PositiveSmallIntegerField(
        help_text="Colocação final na partida (1 para Vencedor, etc.)"
    )
    kill_count = models.PositiveIntegerField(default=0)
    mvp_card = models.ForeignKey(
        Card,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mvp_performances',
        help_text="Carta MVP jogada por este participante na partida (opcional)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('game', 'player')
        ordering = ['game', 'placement']

    def __str__(self):
        player_name = self.player.nickname or self.player.name
        return f"{self.game} - {player_name} ({self.placement}º lugar)"
