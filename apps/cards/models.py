from django.db import models


class Card(models.Model):
    name = models.CharField(max_length=255, unique=True)
    color_identity = models.CharField(max_length=10, blank=True)
    mana_value = models.PositiveIntegerField(
        default=0, help_text="Valor de mana convertido (CMC)"
    )
    is_commander_eligible = models.BooleanField(default=False)
    can_have_partner = models.BooleanField(
        default=False,
        help_text=(
            "Tem a habilidade Partner (inclui a variante 'Friends Forever') — "
            "forma dupla com qualquer outra carta que também tenha Partner"
        ),
    )
    partner_with = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="partnered_by",
        help_text=(
            "Parceiro nomeado e exclusivo (Partner with) — se preenchido, esta "
            "carta só pode formar dupla com essa carta específica"
        ),
    )
    can_choose_background = models.BooleanField(
        default=False,
        help_text="Tem 'Choose a Background' — pode ter um Background como segundo comandante",
    )
    is_background = models.BooleanField(
        default=False,
        help_text=(
            "É um Background — só pode ser comandante ao lado de uma carta com "
            "'Choose a Background', nunca sozinho"
        ),
    )
    has_doctors_companion = models.BooleanField(
        default=False,
        help_text="Tem 'Doctor's companion' — pode formar dupla com qualquer carta 'The Doctor'",
    )
    is_the_doctor = models.BooleanField(
        default=False,
        help_text="É 'The Doctor' — pode formar dupla com qualquer carta 'Doctor's companion'",
    )
    scryfall_oracle_id = models.CharField(
        max_length=36,
        blank=True,
        help_text="Oracle ID do Scryfall (compartilhado entre reimpressões)",
    )
    image_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
