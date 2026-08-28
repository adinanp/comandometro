from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import m2m_changed
from django.dispatch import receiver
from .player import Player
from .card import Card


class Deck(models.Model):
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="decks")
    commanders = models.ManyToManyField(
        Card,
        related_name="decks_as_commander",
        limit_choices_to={"is_commander_eligible": True},
        help_text="Selecione até 2 comandantes válidos",
    )
    color_identity = models.CharField(
        max_length=10,
        blank=True,
        help_text="Identidade de cor calculada automaticamente",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["player", "-is_active"]

    def clean(self):
        super().clean()
        if self.pk and self.commanders.count() > 2:
            raise ValidationError("Um deck não pode ter mais de 2 comandantes.")

    def update_color_identity(self):
        all_colors = "".join(
            [c.color_identity for c in self.commanders.all() if c.color_identity]
        )
        wubrg_order = "WUBRG"
        combined = "".join([color for color in wubrg_order if color in all_colors])
        self.color_identity = combined if combined else "C"
        self.save(update_fields=["color_identity"])

    def display_commanders(self):
        return " / ".join([c.name for c in self.commanders.all()])

    def __str__(self):
        commanders_str = self.display_commanders() or "Sem comandante"
        return f"{commanders_str} ({self.player.nickname or self.player.name})"


@receiver(m2m_changed, sender=Deck.commanders.through)
def update_deck_color_identity(sender, instance, action, **kwargs):
    if action in ["post_add", "post_remove", "post_clear"]:
        instance.update_color_identity()
