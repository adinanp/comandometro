from django.contrib import admin

from .models import Card, Theme


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    """
    A base de cartas normalmente vem do import em massa do MTGJSON
    (`manage.py import_mtgjson`), mas cartas de preview/spoiler (ainda não
    lançadas, fora do AtomicCards.json) precisam poder ser cadastradas na
    mão aqui. Se uma carta cadastrada manualmente tiver o nome exatamente
    igual ao da versão oficial quando ela sair, o próximo import a
    atualiza no lugar em vez de duplicar (o import casa por nome).
    """

    list_display = (
        "name",
        "color_identity",
        "mana_value",
        "is_commander_eligible",
        "can_have_partner",
        "partner_with",
        "can_choose_background",
        "is_background",
    )
    list_filter = (
        "is_commander_eligible",
        "can_have_partner",
        "can_choose_background",
        "is_background",
        "has_doctors_companion",
        "is_the_doctor",
        "color_identity",
    )
    search_fields = ("name",)
    ordering = ("name",)
    fieldsets = (
        (None, {"fields": ("name", "image_url", "color_identity", "mana_value")}),
        (
            "Comandante",
            {
                "fields": (
                    "is_commander_eligible",
                    "can_have_partner",
                    "partner_with",
                    "can_choose_background",
                    "is_background",
                    "has_doctors_companion",
                    "is_the_doctor",
                )
            },
        ),
        (
            "Scryfall",
            {
                "fields": ("scryfall_oracle_id",),
                "classes": ("collapse",),
                "description": "Preenchido automaticamente pelo import em massa — deixe em branco pra uma carta cadastrada na mão.",
            },
        ),
    )


@admin.register(Theme)
class ThemeAdmin(admin.ModelAdmin):
    """Somente leitura: temas só entram/atualizam via `sync_edhrec_themes`."""

    list_display = ("name", "num_decks", "popularity_rank", "summary", "edhrec_synced_at")
    search_fields = ("name", "slug")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
