from django import forms
from django.contrib import admin
from django.http import JsonResponse
from django.urls import path

from .models import (
    Achievement,
    Card,
    Deck,
    Game,
    GameParticipant,
    Player,
    PlayerProfile,
)


class DeckAdminForm(forms.ModelForm):
    class Meta:
        model = Deck
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        player_id = self.initial.get("player")
        if player_id and not self.instance.pk:
            self.fields["player"].widget = forms.HiddenInput()
            self.fields["player"].required = False

    def clean_commanders(self):
        commanders = list(self.cleaned_data.get("commanders", []))
        Deck.validate_commanders(commanders)
        return commanders


class PlayerProfileInline(admin.StackedInline):
    model = PlayerProfile
    can_delete = False
    verbose_name_plural = "Perfil do Jogador"
    fk_name = "player"


class GameParticipantInline(admin.TabularInline):
    model = GameParticipant
    extra = 4
    autocomplete_fields = ["player", "mvp_card", "biggest_creature"]
    fields = (
        "player",
        "deck",
        "placement",
        "kill_count",
        "mvp_card",
        "peak_life_total",
        "board_wipes_count",
        "counterspell_count",
        "complaint_count",
        "is_self_elimination",
        "biggest_creature",
        "biggest_creature_power",
        "starting_seat",
        "felt_salty",
        "fun_rating",
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name in ("mvp_card", "biggest_creature"):
            formfield.widget.can_add_related = False
        return formfield


class AchievementInline(admin.TabularInline):
    model = Achievement
    extra = 1
    autocomplete_fields = ["player"]
    fields = ("title", "detail", "player")


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("id", "display_name", "name", "nickname", "created_at")
    search_fields = ("name", "nickname")
    inlines = [PlayerProfileInline]

    @admin.display(description="Nome de Exibição")
    def display_name(self, obj):
        return str(obj)


@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = ("player", "pronouns", "favorite_color", "favorite_wincon")
    list_filter = ("pronouns", "favorite_color", "favorite_wincon")
    search_fields = ("player__name", "player__nickname")


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


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    form = DeckAdminForm
    list_display = ("display_commanders", "player", "color_identity", "is_active")
    list_filter = ("is_active", "color_identity", "player")
    search_fields = ("commanders__name", "player__name", "player__nickname")
    autocomplete_fields = ["commanders"]

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        player_id = request.GET.get("player")
        if player_id:
            initial["player"] = player_id
        return initial

    def get_fields(self, request, obj=None):
        fields = ["commanders", "is_active"]
        player_id = request.GET.get("player")
        if not player_id and not obj:
            fields.insert(0, "player")
        elif obj:
            fields.insert(0, "player")
        else:
            fields.append("player")
        return fields

    def save_model(self, request, obj, form, change):
        if not change and not getattr(obj, "player_id", None):
            player_id = request.GET.get("player")
            if player_id:
                obj.player_id = player_id
        super().save_model(request, obj, form, change)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "get_game_title",
        "date",
        "win_condition",
        "turn_count",
        "get_winner",
        "created_at",
    )
    list_filter = ("win_condition", "date")
    search_fields = (
        "id",
        "notes",
        "participants__player__name",
        "participants__player__nickname",
    )
    inlines = [GameParticipantInline, AchievementInline]

    @admin.display(description="Partida")
    def get_game_title(self, obj):
        return str(obj)

    @admin.display(description="Vencedor")
    def get_winner(self, obj):
        winner = obj.participants.filter(placement=1).first()
        return str(winner.player) if winner else "-"

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                "get-player-decks/<int:player_id>/",
                self.admin_site.admin_view(self.get_player_decks),
                name="get_player_decks",
            ),
        ]
        return custom_urls + urls

    def get_player_decks(self, request, player_id):
        decks = Deck.objects.filter(player_id=player_id, is_active=True)
        data = [{"id": d.id, "name": str(d)} for d in decks]
        return JsonResponse({"decks": data})

    class Media:
        js = ("core/js/admin_game_participant.js",)


@admin.register(GameParticipant)
class GameParticipantAdmin(admin.ModelAdmin):
    list_display = ("game", "player", "deck", "placement", "kill_count", "mvp_card")
    list_filter = ("placement", "player")
    search_fields = (
        "player__name",
        "player__nickname",
        "deck__commanders__name",
        "game__id",
        "mvp_card__name",
    )
    autocomplete_fields = ["game", "player", "mvp_card"]


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("title", "player", "game", "date")
    list_filter = ("date", "player")
    search_fields = ("title", "detail", "player__name", "player__nickname")
    autocomplete_fields = ["player", "game"]
