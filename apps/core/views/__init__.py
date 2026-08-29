from .dashboard import DashboardView
from .player_profile import PlayerProfileView
from .player_list import PlayerListView
from .player_create import PlayerCreateView
from .my_profile import MyProfileRedirectView
from .game_list import GameListView
from .game_detail import GameDetailView
from .game_create import GameCreateView
from .deck_detail import DeckDetailView
from .deck_create import DeckCreateView
from .deck_create_ajax import DeckCreateAjaxView

__all__ = [
    "DashboardView",
    "PlayerProfileView",
    "PlayerListView",
    "PlayerCreateView",
    "MyProfileRedirectView",
    "GameListView",
    "GameDetailView",
    "GameCreateView",
    "DeckDetailView",
    "DeckCreateView",
    "DeckCreateAjaxView",
]
