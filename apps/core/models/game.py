from django.db import models


class WinConditionChoices(models.TextChoices):
    COMBAT = "combat", "Combate"
    COMBO = "combo", "Combo"
    ENGINE_VALUE = "engine_value", "Engine/Value"
    INFECT = "infect", "Infect"
    SELF_MILL = "self_mill", "Self-Mill"
    HARD_LOCK = "hard_lock", "Hard Lock"
    MILL = "mill", "Mill"
    SOFT_LOCK = "soft_lock", "Soft Lock"
    BURN_LIFELOSS = "burn_lifeloss", "Queima/Perda de Vida"
    COMMANDER_DAMAGE = "commander_damage", "Dano de Comandante"


class Game(models.Model):
    pod = models.ForeignKey(
        "pods.Pod", on_delete=models.CASCADE, related_name="games"
    )
    date = models.DateField(
        null=True, blank=True, help_text="Data em que a partida foi realizada"
    )
    win_condition = models.CharField(
        max_length=30,
        choices=WinConditionChoices.choices,
        blank=True,
        help_text="Forma como o vencedor ganhou o jogo",
    )
    notes = models.TextField(
        blank=True, help_text="Observações ou momentos marcantes da partida"
    )
    turn_count = models.PositiveIntegerField(
        null=True, blank=True, help_text="Número de turnos até o fim da partida"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        date_str = self.date.strftime("%d/%m/%Y") if self.date else "Sem data"
        return f"Jogo #{self.pk} ({date_str})"
