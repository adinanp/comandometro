from django.db import models


class Card(models.Model):
    name = models.CharField(
        max_length=150,
        unique=True,
        help_text="Nome em inglês da carta"
    )
    mana_value = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        default=0.0,
        help_text="Custo de Mana Convertido / Mana Value"
    )
    color_identity = models.CharField(
        max_length=10,
        blank=True,
        help_text="Identidade de cor em letras maiúsculas (ex: 'W', 'UBG', 'C')"
    )
    is_commander_eligible = models.BooleanField(
        default=False,
        help_text="Indica se a carta pode ser Comandante"
    )
    is_partner_eligible = models.BooleanField(
        default=False,
        help_text="Indica se possui Partner, Background, Friends Forever, etc."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def clean(self):
        super().clean()
        if self.color_identity:
            self.color_identity = self.color_identity.upper().strip()

    def get_colors_list(self):
        """Retorna uma lista contendo as letras das cores individuais da carta."""
        return list(self.color_identity) if self.color_identity else []

    def __str__(self):
        colors = self.color_identity if self.color_identity else 'C'
        return f"{self.name} [{colors}]"
