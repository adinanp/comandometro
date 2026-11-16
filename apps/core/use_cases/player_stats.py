"""
Cálculos por jogador compartilhados entre a página de perfil
(`PlayerProfileUseCase`) e o card "Você no pod" do dashboard
(`PlayerPodCardUseCase`).
"""

from datetime import date

from django.db.models import Count, Max

from apps.core.models import Deck, wincon_label


def favorite_wincon(performances):
    """Wincon mais comum entre as partidas em que esse jogador ficou em
    1º lugar."""
    top = (
        performances.filter(placement=1)
        .values("game__win_condition")
        .annotate(count=Count("id"))
        .order_by("-count")
        .first()
    )
    if not top:
        return None
    return {"label": wincon_label(top["game__win_condition"]), "count": top["count"]}

def favorite_color_combo(player):
    """
    Combinação exata de cores (color identity) mais jogada entre os
    decks desse jogador, pesada pelo número de partidas de cada deck —
    não a união de todas as cores já pilotadas, que convergiria pra
    "WUBRG" conforme o jogador testasse mais decks diferentes ao longo
    do tempo e deixaria de dizer qualquer coisa sobre preferência. Dois
    decks diferentes com a mesma combinação somam no mesmo grupo.
    Empate é desempatado pela partida mais recente, mesmo critério dos
    cards de especialista do dashboard.
    """
    decks = Deck.objects.filter(player=player).annotate(
        games=Count("match_performances"),
        last_game=Max("match_performances__game__date"),
    ).filter(games__gt=0)
    buckets = {}
    for identity, games, last_game in decks.values_list(
        "color_identity", "games", "last_game"
    ):
        key = identity or "C"
        bucket = buckets.setdefault(key, {"games": 0, "last_game": None})
        bucket["games"] += games
        if last_game and (bucket["last_game"] is None or last_game > bucket["last_game"]):
            bucket["last_game"] = last_game
    if not buckets:
        return None
    identity, data = max(
        buckets.items(),
        key=lambda item: (item[1]["games"], item[1]["last_game"] or date.min),
    )
    return {"identity": identity, "games": data["games"]}
