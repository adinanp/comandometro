from django.db.models import Avg, Count, F, Max, Sum
from apps.core.models import (
    Achievement,
    Game,
    GameParticipant,
    Player,
    WinConditionChoices,
    wincon_label,
)
from apps.core.use_cases.base import BaseUseCase


class DashboardStatsUseCase(BaseUseCase):
    def perform_request(self, pod, since=None) -> dict:
        games = Game.objects.filter(pod=pod)
        achievements_qs = Achievement.objects.filter(player__pod=pod).select_related("player")
        participants = GameParticipant.objects.filter(game__pod=pod)
        if since:
            games = games.filter(date__gte=since)
            achievements_qs = achievements_qs.filter(date__gte=since)
            participants = participants.filter(game__date__gte=since)

        total_games = games.count()
        games_with_turns = games.exclude(turn_count__isnull=True)
        avg_turn_count = games_with_turns.aggregate(avg=Avg("turn_count"))["avg"]
        avg_turn_count = round(avg_turn_count, 1) if avg_turn_count is not None else None

        # Empate em turn_count é desempatado pela partida mais recente,
        # mesmo critério usado nos outros cards do dashboard.
        fastest = games_with_turns.order_by("turn_count", "-date", "-id").first()
        fastest_game = (
            {"id": fastest.id, "turn_count": fastest.turn_count} if fastest else None
        )

        ranked_players = []
        for player in Player.objects.filter(pod=pod):
            performances = player.match_performances.all()
            if since:
                performances = performances.filter(game__date__gte=since)
            total = performances.count()
            wins = performances.filter(placement=1).count()
            wr = round((wins / total * 100), 1) if total else 0
            ranked_players.append(
                {
                    "id": player.id,
                    "name": player.name,
                    "wins": wins,
                    "total_games": total,
                    "win_rate": wr,
                }
            )
        ranked_players.sort(key=lambda p: (-p["wins"], -p["total_games"]))

        top_player = (
            ranked_players[0]
            if ranked_players and ranked_players[0]["wins"] > 0
            else None
        )

        wincon_counts = (
            games.values("win_condition").annotate(count=Count("id")).order_by("-count")
        )

        wincon_modes = []
        for wc in wincon_counts:
            pct = round((wc["count"] / total_games * 100), 1) if total_games > 0 else 0
            wincon_modes.append(
                {
                    "name": wincon_label(wc["win_condition"]),
                    "value": wc["win_condition"],
                    "count": wc["count"],
                    "percentage": pct,
                }
            )

        top_wincon = wincon_modes[0] if wincon_modes else None

        # Exige pelo menos 2 votos pra evitar destacar uma carta MVP marcada
        # uma única vez como se fosse "a preferida do pod".
        top_mvp_query = (
            participants.filter(mvp_card__isnull=False)
            .values("mvp_card", "mvp_card__name")
            .annotate(count=Count("id"))
            .filter(count__gte=2)
            .order_by("-count")
            .first()
        )
        top_mvp = (
            {"id": top_mvp_query["mvp_card"], "name": top_mvp_query["mvp_card__name"]}
            if top_mvp_query
            else None
        )

        achievements = achievements_qs.order_by("-date", "-id")[:5]

        return {
            "total_games": total_games,
            "avg_turn_count": avg_turn_count,
            "fastest_game": fastest_game,
            "top_player": top_player,
            "top_wincon": top_wincon,
            "top_mvp": top_mvp,
            "ranked_players": self._pad(ranked_players[:5], 5),
            "wincon_modes": self._pad(wincon_modes[:5], 5),
            "achievements": achievements,
            "wincon_specialists": self._wincon_specialists(pod, since),
            "biggest_killer": self._biggest_killer(pod, since),
        }

    def _pad(self, rows, size):
        """
        Completa a lista com linhas vazias (`{"empty": True}`) até `size` —
        os boxes de TOP 5 no dashboard usam isso pra manter altura fixa e
        deixar explícito que mais linhas serão preenchidas conforme os dados
        crescem, em vez de encolher o box quando há poucos dados.
        """
        return rows + [{"empty": True}] * (size - len(rows))

    def _wincon_specialists(self, pod, since):
        """
        "Maior Combeiro/Agressor" e "Rei do Voltron" — de quem mais vence com cada
        wincon específica, cruzando vitórias (placement=1) com a wincon da
        partida. Só usa as wincons pré-definidas (combo/combate/dano de
        comandante), não as customizadas — são as três com nome e ícone
        fixo na tela; uma wincon nova digitada pelo usuário não vira
        automaticamente uma quarta categoria aqui. Empate em número de
        vitórias é desempatado pela vitória mais recente.
        """
        categories = [
            ("combeiro", "🎲", "Maior Combeiro", WinConditionChoices.COMBO),
            ("agressor", "⚔️", "Maior Agressor", WinConditionChoices.COMBAT),
            ("comandeiro", "👑", "Rei do Voltron", WinConditionChoices.COMMANDER_DAMAGE),
        ]
        specialists = []
        for key, icon, label, win_condition in categories:
            wins = GameParticipant.objects.filter(
                game__pod=pod, placement=1, game__win_condition=win_condition
            )
            if since:
                wins = wins.filter(game__date__gte=since)
            top = (
                wins.values("player_id", "player__name")
                .annotate(count=Count("id"), last_win=Max("game__date"))
                .order_by("-count", F("last_win").desc(nulls_last=True))
                .first()
            )
            specialists.append(
                {
                    "key": key,
                    "icon": icon,
                    "label": label,
                    "player_id": top["player_id"] if top else None,
                    "player_name": top["player__name"] if top else None,
                    "wins": top["count"] if top else 0,
                }
            )
        return specialists

    def _biggest_killer(self, pod, since):
        """
        "Maior Matador" — quem mais eliminou outros jogadores no total,
        somando `kill_count` de todas as partidas. Assim como duração
        média, é opcional/impreciso (depende de quem lembra de preencher),
        mas divertido de acompanhar. Empate no total é desempatado pela
        partida mais recente em que o jogador participou.
        """
        performances = GameParticipant.objects.filter(game__pod=pod)
        if since:
            performances = performances.filter(game__date__gte=since)
        top = (
            performances.values("player_id", "player__name")
            .annotate(total_kills=Sum("kill_count"), last_game=Max("game__date"))
            .order_by("-total_kills", F("last_game").desc(nulls_last=True))
            .first()
        )
        if not top or not top["total_kills"]:
            return None
        return {
            "player_id": top["player_id"],
            "player_name": top["player__name"],
            "kills": top["total_kills"],
        }
