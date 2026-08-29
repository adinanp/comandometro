from django.db.models import Count
from django.db.models.functions import TruncMonth

from apps.core.models import Deck, Game, GameParticipant, Player
from apps.core.use_cases.base import BaseUseCase

POINTS_BY_PLACEMENT = {1: 4, 2: 2, 3: 1}


class PodInsightsUseCase(BaseUseCase):
    def perform_request(self, pod, since=None) -> dict:
        return {
            "color_identity_stats": self._color_identity_stats(pod, since),
            "color_count_stats": self._color_count_stats(pod, since),
            "wincon_trend": self._wincon_trend(pod, since),
            "points_ranking": self._points_ranking(pod, since),
            "top_commanders_qualified": self._top_commanders_qualified(pod, since),
            "seat_stats": self._seat_stats(pod, since),
            "records": self._records(pod),
        }

    def _color_identity_stats(self, pod, since):
        stats = []
        for color in "WUBRG":
            decks_with_color = Deck.objects.filter(
                color_identity__contains=color, player__pod=pod
            )
            performances = GameParticipant.objects.filter(deck__in=decks_with_color)
            if since:
                performances = performances.filter(game__date__gte=since)
            games = performances.count()
            wins = performances.filter(placement=1).count()
            win_rate = round((wins / games * 100), 1) if games else 0
            stats.append(
                {"color": color, "games": games, "wins": wins, "win_rate": win_rate}
            )
        return stats

    def _color_count_stats(self, pod, since):
        buckets = {n: {"games": 0, "wins": 0} for n in range(6)}
        for deck in Deck.objects.filter(player__pod=pod):
            performances = deck.match_performances.all()
            if since:
                performances = performances.filter(game__date__gte=since)
            games = performances.count()
            wins = performances.filter(placement=1).count()
            num_colors = (
                0 if deck.color_identity in ("", "C") else len(deck.color_identity)
            )
            buckets[num_colors]["games"] += games
            buckets[num_colors]["wins"] += wins

        stats = []
        for num_colors, totals in sorted(buckets.items()):
            games = totals["games"]
            wins = totals["wins"]
            win_rate = round((wins / games * 100), 1) if games else 0
            stats.append(
                {
                    "colors": num_colors,
                    "games": games,
                    "wins": wins,
                    "win_rate": win_rate,
                }
            )
        return stats

    def _wincon_trend(self, pod, since):
        games = Game.objects.filter(pod=pod).exclude(date__isnull=True)
        if since:
            games = games.filter(date__gte=since)
        trend = (
            games.annotate(month=TruncMonth("date"))
            .values("month", "win_condition")
            .annotate(count=Count("id"))
            .order_by("month", "win_condition")
        )
        return list(trend)

    def _points_ranking(self, pod, since):
        ranking = []
        for player in Player.objects.filter(pod=pod):
            performances = player.match_performances.all()
            if since:
                performances = performances.filter(game__date__gte=since)
            points = sum(
                POINTS_BY_PLACEMENT.get(p.placement, 0) for p in performances
            )
            ranking.append({"player": player, "points": points})
        ranking.sort(key=lambda row: row["points"], reverse=True)
        return ranking

    def _top_commanders_qualified(self, pod, since):
        qualified = []
        for deck in Deck.objects.filter(player__pod=pod):
            performances = deck.match_performances.all()
            if since:
                performances = performances.filter(game__date__gte=since)
            games = performances.count()
            if games < 5:
                continue
            wins = performances.filter(placement=1).count()
            win_rate = round((wins / games * 100), 1)
            if win_rate >= 20:
                qualified.append(
                    {"deck": deck, "games": games, "wins": wins, "win_rate": win_rate}
                )
        qualified.sort(key=lambda row: row["win_rate"], reverse=True)
        return qualified

    def _seat_stats(self, pod, since):
        performances = GameParticipant.objects.filter(game__pod=pod).exclude(
            starting_seat__isnull=True
        )
        if since:
            performances = performances.filter(game__date__gte=since)

        buckets = {}
        for performance in performances:
            seat = performance.starting_seat
            buckets.setdefault(seat, {"games": 0, "wins": 0})
            buckets[seat]["games"] += 1
            if performance.placement == 1:
                buckets[seat]["wins"] += 1

        stats = []
        for seat, totals in sorted(buckets.items()):
            win_rate = round((totals["wins"] / totals["games"] * 100), 1)
            stats.append(
                {
                    "seat": seat,
                    "games": totals["games"],
                    "wins": totals["wins"],
                    "win_rate": win_rate,
                }
            )
        return stats

    def _records(self, pod):
        pod_participants = GameParticipant.objects.filter(game__pod=pod)

        def top_by(field):
            obj = (
                pod_participants.select_related("player", "game")
                .order_by(f"-{field}")
                .first()
            )
            return obj if obj and getattr(obj, field) > 0 else None

        most_life = (
            pod_participants.select_related("player", "game")
            .exclude(peak_life_total__isnull=True)
            .order_by("-peak_life_total")
            .first()
        )
        biggest_creature = (
            pod_participants.select_related("player", "game", "biggest_creature")
            .exclude(biggest_creature__isnull=True)
            .order_by("-biggest_creature_power")
            .first()
        )
        fastest_game_no_combo = (
            Game.objects.filter(pod=pod)
            .exclude(win_condition="combo")
            .exclude(turn_count__isnull=True)
            .order_by("turn_count")
            .first()
        )
        fastest_game_combo = (
            Game.objects.filter(pod=pod, win_condition="combo")
            .exclude(turn_count__isnull=True)
            .order_by("turn_count")
            .first()
        )

        return {
            "board_wipes": top_by("board_wipes_count"),
            "counterspells": top_by("counterspell_count"),
            "complaints": top_by("complaint_count"),
            "most_life": most_life,
            "biggest_creature": biggest_creature,
            "self_eliminations_count": pod_participants.filter(
                is_self_elimination=True
            ).count(),
            "fastest_game_no_combo": fastest_game_no_combo,
            "fastest_game_combo": fastest_game_combo,
            "saltiest_deck": self._saltiest_deck(pod),
            "most_fun_deck": self._most_fun_deck(pod),
        }

    def _saltiest_deck(self, pod):
        best = None
        for deck in Deck.objects.filter(player__pod=pod):
            wins = GameParticipant.objects.filter(deck=deck, placement=1)
            if wins.count() < 3:
                continue
            salty_reactions = 0
            eligible_reactions = 0
            for win in wins:
                opponents = GameParticipant.objects.filter(game=win.game).exclude(
                    placement=1
                )
                eligible_reactions += opponents.count()
                salty_reactions += opponents.filter(felt_salty=True).count()
            if eligible_reactions == 0:
                continue
            salt_percentage = round((salty_reactions / eligible_reactions * 100), 1)
            if best is None or salt_percentage > best["salt_percentage"]:
                best = {"deck": deck, "salt_percentage": salt_percentage}
        return best

    def _most_fun_deck(self, pod):
        best = None
        for deck in Deck.objects.filter(player__pod=pod):
            ratings = list(
                GameParticipant.objects.filter(deck=deck)
                .exclude(fun_rating__isnull=True)
                .values_list("fun_rating", flat=True)
            )
            if len(ratings) < 3:
                continue
            avg_rating = round(sum(ratings) / len(ratings), 1)
            if best is None or avg_rating > best["avg_rating"]:
                best = {"deck": deck, "avg_rating": avg_rating}
        return best
