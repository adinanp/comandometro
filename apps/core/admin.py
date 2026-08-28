from django.contrib import admin
from .models import (
    Player,
    PlayerProfile,
    Card,
    Deck,
    Game,
    GameParticipant,
    Achievement,
)


class PlayerProfileInline(admin.StackedInline):
    model = PlayerProfile
    can_delete = False
    verbose_name_plural = "Perfil do Jogador"
    fk_name = "player"


class GameParticipantInline(admin.TabularInline):
    model = GameParticipant
    extra = 4
    autocomplete_fields = ["player", "deck", "mvp_card"]
    fields = ("player", "deck", "placement", "kill_count", "mvp_card")


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
        "is_partner_eligible",
    )
    list_filter = ("is_commander_eligible", "is_partner_eligible", "color_identity")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ("display_commanders", "player", "color_identity", "is_active")
    list_filter = ("is_active", "color_identity", "player")
    search_fields = ("commanders__name", "player__name", "player__nickname")
    autocomplete_fields = ["player", "commanders"]

    @admin.display(description="Comandante(s)")
    def display_commanders(self, obj):
        return obj.display_commanders() or "Sem comandante"


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "get_game_title",
        "date",
        "win_condition",
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
    autocomplete_fields = ["game", "player", "deck", "mvp_card"]


@admin.register(Achievement)
class AchievementAdmin(admin.ModelAdmin):
    list_display = ("title", "player", "game", "date")
    list_filter = ("date", "player")
    search_fields = ("title", "detail", "player__name", "player__nickname")
    autocomplete_fields = ["player", "game"]
