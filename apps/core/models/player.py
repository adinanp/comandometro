from django.conf import settings
from django.db import models


class PronounChoices(models.TextChoices):
    HE_HIM = "he_him", "Ele/Dele"
    SHE_HER = "she_her", "Ela/Dela"
    THEY_THEM = "they_them", "Elu/Delu"
    OTHER = "other", "Outro / Prefiro não informar"


class Player(models.Model):
    pod = models.ForeignKey(
        "pods.Pod", on_delete=models.CASCADE, related_name="players"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="players",
        help_text="Conta vinculada, se o jogador tiver login (opcional — permite jogador convidado)",
    )
    name = models.CharField(
        max_length=100, help_text="Nome completo ou oficial do jogador"
    )
    nickname = models.CharField(
        max_length=50, blank=True, help_text="Apelido usado nas partidas e tabelas"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ("pod", "name")
        ordering = ["name"]

    def __str__(self):
        return str(self.nickname) if self.nickname else str(self.name)


class PlayerProfile(models.Model):
    player = models.OneToOneField(
        Player, on_delete=models.CASCADE, related_name="profile"
    )
    pronouns = models.CharField(
        max_length=20,
        choices=PronounChoices.choices,
        default=PronounChoices.HE_HIM,
        blank=True,
    )
    custom_pronouns = models.CharField(
        max_length=30, blank=True, help_text="Usado se o pronome for 'Outro'"
    )
    favorite_color = models.CharField(max_length=50, blank=True)
    favorite_wincon = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Perfil de {self.player}"
