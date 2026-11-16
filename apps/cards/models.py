from decimal import ROUND_HALF_UP, Decimal

from django.db import models


class Card(models.Model):
    name = models.CharField(max_length=255, unique=True)
    color_identity = models.CharField(max_length=10, blank=True)
    mana_value = models.PositiveIntegerField(
        default=0, blank=True, help_text="Valor de mana convertido (CMC)"
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


class Theme(models.Model):
    """
    Tema/tag de EDH do EDHREC (Voltron, Aristocrats, Elves...). Dado global,
    carregado por `manage.py sync_edhrec_themes` — nunca consultado online
    durante o sorteio. O `summary` nasce da LLM na primeira vez que o tema
    é sorteado.
    """

    slug = models.CharField(max_length=120, unique=True)
    name = models.CharField(max_length=120)
    num_decks = models.PositiveIntegerField(default=0)
    popularity_rank = models.PositiveIntegerField(default=0)
    top_commanders = models.JSONField(
        default=list,
        blank=True,
        help_text='Lista ordenada [{"name", "num_decks"}] dos top comandantes',
    )
    art_crop_url = models.URLField(blank=True)
    summary = models.CharField(max_length=160, blank=True)
    summary_model = models.CharField(max_length=80, blank=True)
    summary_generated_at = models.DateTimeField(null=True, blank=True)
    edhrec_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["popularity_rank", "name"]

    def __str__(self):
        return self.name

    @property
    def edhrec_url(self):
        return f"https://edhrec.com/tags/{self.slug}"

    def top_commander_names(self, limit=3):
        return [c["name"] for c in (self.top_commanders or [])[:limit]]

    def display_num_decks(self):
        if self.num_decks >= 1000:
            thousands = str(
                (Decimal(self.num_decks) / 1000).quantize(
                    Decimal("0.1"), rounding=ROUND_HALF_UP
                )
            ).removesuffix(".0")
            return f"{thousands.replace('.', ',')} mil decks"
        return f"{self.num_decks} deck" + ("" if self.num_decks == 1 else "s")
