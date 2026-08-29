from django.core.validators import MaxValueValidator, MinValueValidator
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
    peak_life_total = models.IntegerField(
        null=True, blank=True, help_text="Vida mais alta atingida na partida"
    )
    board_wipes_count = models.PositiveIntegerField(default=0)
    counterspell_count = models.PositiveIntegerField(default=0)
    complaint_count = models.PositiveIntegerField(
        default=0, help_text="Quantas vezes o participante reclamou na partida"
    )
    is_self_elimination = models.BooleanField(
        default=False,
        help_text="O participante foi eliminado por uma ação própria (não por outro jogador)"
    )
    biggest_creature = models.ForeignKey(
        Card,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biggest_creature_performances',
        help_text="Maior criatura que bateu na mesa nesta partida"
    )
    biggest_creature_power = models.PositiveIntegerField(
        null=True, blank=True, help_text="Poder da criatura alcançado nesta partida"
    )
    starting_seat = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Posição inicial na mesa (1 = primeiro a jogar)"
    )
    felt_salty = models.BooleanField(
        default=False,
        help_text="Marcado por quem NÃO venceu, se achou a vitória do adversário irritante"
    )
    fun_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Nota de diversão da partida (1 a 5) dada por este participante"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('game', 'player')
        ordering = ['game', 'placement']

    def __str__(self):
        player_name = self.player.nickname or self.player.name
        return f"{self.game} - {player_name} ({self.placement}º lugar)"
