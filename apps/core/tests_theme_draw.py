from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from zoneinfo import ZoneInfo

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.cards.models import Theme
from apps.core.models import Player, ThemeDraw, ThemeDrawSeat
from apps.core.use_cases import DrawThemesUseCase
from apps.core.use_cases.draw_themes import week_start
from apps.pods.models import Pod

SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def make_themes(count, prefix="tema"):
    return [
        Theme.objects.create(slug=f"{prefix}-{i}", name=f"Tema {i}", popularity_rank=i)
        for i in range(count)
    ]


class ThemeDrawFixtureMixin:
    def setUp(self):
        self.pod = Pod.objects.create(name="Pod de Teste")
        self.players = [
            Player.objects.create(pod=self.pod, name=name)
            for name in ("Ana", "Beto", "Caio", "Duda")
        ]
        self.other_pod = Pod.objects.create(name="Outro Pod")
        self.outsider = Player.objects.create(pod=self.other_pod, name="Zé")


class ThemeDrawModelTests(ThemeDrawFixtureMixin, TestCase):
    def test_seat_clean_rejects_player_from_other_pod(self):
        theme = make_themes(1)[0]
        draw = ThemeDraw.objects.create(pod=self.pod)
        seat = ThemeDrawSeat(draw=draw, player=self.outsider, theme=theme, position=0)

        with self.assertRaises(ValidationError):
            seat.full_clean()


class WeekStartTests(TestCase):
    def test_week_start_sunday_night_brasilia(self):
        # Domingo 15/11 23:30 em São Paulo = segunda 16/11 02:30 UTC.
        sunday_night = datetime(2026, 11, 16, 2, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(
            week_start(sunday_night), datetime(2026, 11, 9, 0, 0, tzinfo=SAO_PAULO)
        )

        monday_early = datetime(2026, 11, 16, 3, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(
            week_start(monday_early), datetime(2026, 11, 16, 0, 0, tzinfo=SAO_PAULO)
        )


class DrawThemesUseCaseTests(ThemeDrawFixtureMixin, TestCase):
    def _draw(self, players=None, pod=None):
        return DrawThemesUseCase().execute(pod or self.pod, players or self.players)

    def _theme_ids(self, draw):
        return {seat.theme_id for seat in draw.seats.all()}

    def test_draw_creates_four_distinct_seats_in_order(self):
        make_themes(10)

        draw = self._draw()

        seats = list(draw.seats.all())
        self.assertEqual(len(seats), 4)
        self.assertEqual(len({s.theme_id for s in seats}), 4)
        self.assertEqual([s.position for s in seats], [0, 1, 2, 3])
        self.assertEqual([s.player for s in seats], self.players)

    def test_excludes_themes_drawn_this_week_in_same_pod(self):
        themes = make_themes(8)

        first = self._draw()
        second = self._draw()

        self.assertEqual(self._theme_ids(first) | self._theme_ids(second), {t.id for t in themes})
        self.assertFalse(self._theme_ids(first) & self._theme_ids(second))

    def test_ignores_other_pod_and_previous_week(self):
        make_themes(4)
        other_players = [self.outsider] + [
            Player.objects.create(pod=self.other_pod, name=n) for n in ("X", "Y", "Z")
        ]
        self._draw(players=other_players, pod=self.other_pod)
        last_week = self._draw()
        ThemeDraw.objects.filter(pk=last_week.pk).update(
            created_at=timezone.now() - timedelta(days=8)
        )

        # Com só 4 temas, o fallback esconderia uma exclusão indevida no
        # sorteio em si; por isso checamos a lista de elegíveis diretamente.
        self.assertEqual(DrawThemesUseCase.eligible_themes(self.pod).count(), 4)

    def test_falls_back_when_fewer_than_four_eligible(self):
        make_themes(5)
        self._draw()

        draw = self._draw()

        self.assertEqual(len(self._theme_ids(draw)), 4)

    def test_rejects_wrong_player_count_and_foreign_player(self):
        make_themes(10)
        invalid = [
            self.players[:3],
            self.players[:3] + [self.players[0]],
            self.players[:3] + [self.outsider],
            self.players + [Player.objects.create(pod=self.pod, name="Eva")],
        ]
        for players in invalid:
            with self.subTest(players=[p.name for p in players]):
                with self.assertRaises(ValidationError):
                    self._draw(players=players)

        self.assertEqual(ThemeDraw.objects.count(), 0)

    def test_rejects_empty_catalog(self):
        with self.assertRaises(ValidationError):
            self._draw()

        self.assertEqual(ThemeDraw.objects.count(), 0)
