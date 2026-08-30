from .dashboard import DashboardView
from .player_profile import PlayerProfileView
from .player_list import PlayerListView
from .my_profile import MyProfileView
from .my_decks import MyDecksView, DeckDeleteView
from .game_list import GameListView
from .game_detail import GameDetailView
from .game_create import GameCreateView
from .game_update import GameUpdateView
from .deck_detail import DeckDetailView
from .deck_create import DeckCreateView
from .deck_create_ajax import DeckCreateAjaxView

__all__ = [
    "DashboardView",
    "PlayerProfileView",
    "PlayerListView",
    "MyProfileView",
    "MyDecksView",
    "DeckDeleteView",
    "GameListView",
    "GameDetailView",
    "GameCreateView",
    "GameUpdateView",
    "DeckDetailView",
    "DeckCreateView",
    "DeckCreateAjaxView",
]
