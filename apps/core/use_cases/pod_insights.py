from django.db.models import Count
from django.db.models.functions import TruncMonth

from apps.core.models import Deck, Game, GameParticipant, Player, wincon_label
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
        rows = list(trend)
        for row in rows:
            row["win_condition"] = wincon_label(row["win_condition"])
        return rows

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

