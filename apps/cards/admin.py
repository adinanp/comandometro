from django.contrib import admin

from .models import Card


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
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

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False
