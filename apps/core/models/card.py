from django.db import models


class Card(models.Model):
    name = models.CharField(max_length=255, unique=True)
    color_identity = models.CharField(max_length=10, blank=True)
    mana_value = models.PositiveIntegerField(
        default=0, help_text="Valor de mana convertido (CMC)"
    )
    is_commander_eligible = models.BooleanField(default=False)
    is_partner_eligible = models.BooleanField(default=False)
    scryfall_id = models.CharField(max_length=36, blank=True)
    image_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
