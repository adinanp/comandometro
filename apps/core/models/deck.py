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
        if self.pk:
            self.validate_commanders(list(self.commanders.all()))

    @staticmethod
    def validate_commanders(commanders):
        """
        Valida se a combinação de comandantes é legal segundo as regras de
        Magic: no máximo 2, e se forem 2, precisam poder formar dupla de
        verdade (Partner, Partner with nomeado, Choose a Background +
        Background, ou Doctor's companion + The Doctor). Um Background
        sozinho também não é um comandante válido.
        """
        if len(commanders) > 2:
            raise ValidationError("Um deck não pode ter mais de 2 comandantes.")

        if len(commanders) == 2:
            first, second = commanders
            if not Deck.can_pair(first, second):
                raise ValidationError(
                    f'"{first.name}" e "{second.name}" não podem formar dupla de '
                    "comandantes — nenhuma habilidade (Partner, Partner with, "
                    "Choose a Background, Doctor's companion) permite essa "
                    "combinação."
                )
        elif len(commanders) == 1 and commanders[0].is_background:
            raise ValidationError(
                f'"{commanders[0].name}" é um Background e não pode ser '
                "comandante sozinho — precisa formar dupla com uma carta que "
                "tenha 'Choose a Background'."
            )

    @staticmethod
    def can_pair(first, second):
        """
        Duas cartas podem ser comandantes juntas se alguma habilidade real do
        jogo permitir essa combinação específica.
        """
        # Partner with — pareamento nomeado e exclusivo (ignora Partner genérico)
        if (
            first.partner_with_id
            and first.partner_with_id == second.id
            and second.partner_with_id == first.id
        ):
            return True

        # Choose a Background + Background
        if first.can_choose_background and second.is_background:
            return True
        if second.can_choose_background and first.is_background:
            return True

        # Doctor's companion + The Doctor
        if first.has_doctors_companion and second.is_the_doctor:
            return True
        if second.has_doctors_companion and first.is_the_doctor:
            return True

        # Partner genérico (inclui a variante "Friends Forever") — só vale se
        # nenhuma das duas tiver um parceiro nomeado específico, já que
        # "Partner with" é exclusivo e não cai de volta pro Partner genérico.
        if (
            first.can_have_partner
            and second.can_have_partner
            and not first.partner_with_id
            and not second.partner_with_id
        ):
            return True

        return False

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
