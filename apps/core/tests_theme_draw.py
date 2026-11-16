import http.client
import io
import urllib.error
from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest import mock
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.cards.models import Theme
from apps.core.models import Player, ThemeDraw, ThemeDrawSeat
from apps.core.use_cases import DrawThemesUseCase, ThemeDrawRecapUseCase
from apps.core.use_cases.draw_themes import week_start
from apps.core.use_cases.theme_draw_recap import fit_text, load_font
from apps.pods.models import Membership, Pod

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

    def test_locks_pod_before_reading_eligible_themes(self):
        # Dois sorteios simultâneos no mesmo pod não podem ler a mesma lista
        # de elegíveis: o pod é travado antes de consultar os temas da semana.
        make_themes(10)

        with CaptureQueriesContext(connection) as queries:
            self._draw()

        sqls = [q["sql"] for q in queries.captured_queries]
        lock_index = next(
            i for i, sql in enumerate(sqls) if "FOR UPDATE" in sql and "pods_pod" in sql
        )
        seat_read_index = next(
            i for i, sql in enumerate(sqls) if "core_themedrawseat" in sql and "SELECT" in sql
        )
        self.assertLess(lock_index, seat_read_index)

    def test_rejects_empty_catalog(self):
        with self.assertRaises(ValidationError):
            self._draw()

        self.assertEqual(ThemeDraw.objects.count(), 0)


SUMMARY = "apps.cards.use_cases.theme_summary.EnsureThemeSummaryUseCase.perform_request"


class ThemeDrawViewMixin(ThemeDrawFixtureMixin):
    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(username="ana", password="x")
        Membership.objects.create(pod=self.pod, user=self.user)
        self.client.force_login(self.user)
        self.create_url = reverse("core:theme-draw-create", kwargs={"pod_slug": self.pod.slug})

    def _themes_with_data(self, count=6):
        themes = make_themes(count)
        for theme in themes:
            theme.num_decks = 62437
            theme.top_commanders = [
                {"name": f"Cmd {theme.pk}-{i}", "num_decks": 10 - i} for i in range(4)
            ]
            theme.save()
        return themes

    def _draw(self):
        self._themes_with_data()
        return DrawThemesUseCase().execute(self.pod, self.players)

    def _urls(self, draw, theme_id):
        kwargs = {"pod_slug": self.pod.slug, "pk": draw.pk}
        return {
            "create": self.create_url,
            "detail": reverse("core:theme-draw-detail", kwargs=kwargs),
            "summary": reverse("core:theme-summary", kwargs={**kwargs, "theme_id": theme_id}),
        }


class ThemeDrawViewTests(ThemeDrawViewMixin, TestCase):
    def test_non_member_gets_404(self):
        draw = self._draw()
        urls = self._urls(draw, draw.seats.first().theme_id)
        outsider = get_user_model().objects.create_user(username="ze", password="x")
        self.client.force_login(outsider)

        for name, url in urls.items():
            with self.subTest(url=name):
                self.assertEqual(self.client.get(url).status_code, 404)

    def test_post_with_four_players_creates_draw_and_redirects(self):
        self._themes_with_data()

        response = self.client.post(self.create_url, {"players": [p.pk for p in self.players]})

        draw = ThemeDraw.objects.get()
        self.assertRedirects(
            response,
            reverse("core:theme-draw-detail", kwargs={"pod_slug": self.pod.slug, "pk": draw.pk}),
        )
        self.assertEqual(draw.created_by, self.user)
        self.assertEqual(draw.seats.count(), 4)

    def test_invalid_selections_show_error(self):
        self._themes_with_data()
        eva = Player.objects.create(pod=self.pod, name="Eva")
        invalid = {
            "três": [p.pk for p in self.players[:3]],
            "cinco": [p.pk for p in self.players] + [eva.pk],
            "outro pod": [p.pk for p in self.players[:3]] + [self.outsider.pk],
        }
        for label, ids in invalid.items():
            with self.subTest(label):
                response = self.client.post(self.create_url, {"players": ids})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)

        self.assertEqual(ThemeDraw.objects.count(), 0)

    def test_repeated_player_id_is_rejected(self):
        self._themes_with_data()
        a, b, c, _ = self.players

        response = self.client.post(self.create_url, {"players": [a.pk, a.pk, b.pk, c.pk]})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["form"].errors)
        self.assertEqual(ThemeDraw.objects.count(), 0)

    def test_summary_endpoint_unknown_theme_returns_404(self):
        draw = self._draw()

        with mock.patch(SUMMARY) as generate:
            response = self.client.get(self._urls(draw, 999999)["summary"])

        self.assertEqual(response.status_code, 404)
        generate.assert_not_called()

    def test_pod_with_fewer_than_four_players_shows_message(self):
        self.players[3].delete()

        response = self.client.get(self.create_url)

        self.assertContains(response, "precisa de pelo menos 4 jogadores")

    def test_empty_catalog_shows_friendly_error(self):
        response = self.client.post(self.create_url, {"players": [p.pk for p in self.players]})

        self.assertContains(response, "catálogo de temas ainda não foi carregado")
        self.assertEqual(ThemeDraw.objects.count(), 0)

    def test_detail_shows_cards(self):
        draw = self._draw()
        seat = draw.seats.first()

        response = self.client.get(self._urls(draw, seat.theme_id)["detail"])

        self.assertContains(response, seat.player.name)
        self.assertContains(response, seat.theme.name)
        self.assertContains(response, "62,4 mil decks")
        for name in seat.theme.top_commander_names():
            self.assertContains(response, name)
        self.assertNotContains(response, seat.theme.top_commanders[3]["name"])

    def test_detail_with_theme_without_commanders(self):
        draw = self._draw()
        Theme.objects.update(top_commanders=[], art_crop_url="")

        response = self.client.get(self._urls(draw, 0)["detail"])

        self.assertEqual(response.status_code, 200)

    def test_detail_marks_cards_without_summary_for_fetch(self):
        draw = self._draw()
        seats = list(draw.seats.all())
        Theme.objects.filter(pk=seats[0].theme_id).update(summary="Resumo pronto.")

        response = self.client.get(self._urls(draw, 0)["detail"])

        self.assertContains(response, "Resumo pronto.")
        self.assertNotContains(response, self._urls(draw, seats[0].theme_id)["summary"])
        self.assertContains(
            response, f'data-summary-url="{self._urls(draw, seats[1].theme_id)["summary"]}"'
        )

    def test_summary_endpoint_returns_json(self):
        draw = self._draw()
        theme_id = draw.seats.first().theme_id

        with mock.patch(SUMMARY, return_value="Texto gerado."):
            response = self.client.get(self._urls(draw, theme_id)["summary"])

        self.assertEqual(response.json(), {"summary": "Texto gerado."})

    def test_summary_endpoint_rejects_theme_not_in_draw(self):
        draw = self._draw()
        used = set(draw.seats.values_list("theme_id", flat=True))
        unused = Theme.objects.exclude(pk__in=used).first()
        other_players = [self.outsider] + [
            Player.objects.create(pod=self.other_pod, name=n) for n in ("X", "Y", "Z")
        ]
        foreign_draw = DrawThemesUseCase().execute(self.other_pod, other_players)
        foreign_url = reverse(
            "core:theme-summary",
            kwargs={
                "pod_slug": self.pod.slug,
                "pk": foreign_draw.pk,
                "theme_id": foreign_draw.seats.first().theme_id,
            },
        )

        with mock.patch(SUMMARY) as generate:
            self.assertEqual(
                self.client.get(self._urls(draw, unused.pk)["summary"]).status_code, 404
            )
            self.assertEqual(self.client.get(foreign_url).status_code, 404)
        generate.assert_not_called()


RECAP_URLOPEN = "apps.core.use_cases.theme_draw_recap.urllib.request.urlopen"


def _jpeg_response(*args, **kwargs):
    buffer = io.BytesIO()
    Image.new("RGB", (10, 10), "purple").save(buffer, format="JPEG")
    response = mock.MagicMock()
    response.read.return_value = buffer.getvalue()
    response.__enter__.return_value = response
    return response


class ThemeDrawRecapTests(ThemeDrawViewMixin, TestCase):
    def _recap_url(self, draw):
        return reverse(
            "core:theme-draw-recap", kwargs={"pod_slug": self.pod.slug, "pk": draw.pk}
        )

    def _with_art(self):
        draw = self._draw()
        Theme.objects.update(art_crop_url="https://x/art.jpg", summary="Resumo curto.")
        return draw

    def test_recap_is_png_1080x1350(self):
        draw = self._with_art()

        with mock.patch(RECAP_URLOPEN, side_effect=_jpeg_response):
            png = ThemeDrawRecapUseCase().execute(draw)

        image = Image.open(io.BytesIO(png))
        self.assertEqual(image.format, "PNG")
        self.assertEqual(image.size, (1080, 1350))

    def test_recap_does_not_call_gemini(self):
        draw = self._draw()  # temas sem resumo

        with mock.patch(RECAP_URLOPEN, side_effect=_jpeg_response), mock.patch(
            SUMMARY
        ) as ensure, mock.patch("apps.cards.llm.generate_text") as generate:
            ThemeDrawRecapUseCase().execute(draw)

        ensure.assert_not_called()
        generate.assert_not_called()

    def test_recap_survives_missing_art_and_commanders(self):
        draw = self._draw()
        Theme.objects.update(top_commanders=[])
        theme = draw.seats.first().theme
        Theme.objects.filter(pk=theme.pk).update(art_crop_url="https://x/broken.jpg")

        with mock.patch(RECAP_URLOPEN, side_effect=urllib.error.URLError("down")):
            png = ThemeDrawRecapUseCase().execute(draw)

        self.assertEqual(Image.open(io.BytesIO(png)).size, (1080, 1350))

    def test_fit_text_truncates_long_names(self):
        canvas = ImageDraw.Draw(Image.new("RGB", (10, 10)))
        font = load_font("body", 20)

        lines = fit_text(canvas, "X" * 60, font, max_width=400, max_lines=1)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].endswith("…"))
        self.assertLessEqual(canvas.textlength(lines[0], font=font), 400)

        summary = ("Sacrifica as próprias criaturas por valor e drena a mesa a cada "
                   "morte, com peças como Blood Artist e mais.")
        lines = fit_text(canvas, summary, font, max_width=300, max_lines=2)
        self.assertLessEqual(len(lines), 2)
        for line in lines:
            self.assertLessEqual(canvas.textlength(line, font=font), 300)

    def test_recap_view_requires_member_and_returns_png(self):
        draw = self._with_art()

        with mock.patch(RECAP_URLOPEN, side_effect=_jpeg_response):
            response = self.client.get(self._recap_url(draw))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response["Content-Type"], "image/png")

            outsider = get_user_model().objects.create_user(username="ze", password="x")
            self.client.force_login(outsider)
            self.assertEqual(self.client.get(self._recap_url(draw)).status_code, 404)


class ThemeDrawRecapRobustnessTests(ThemeDrawViewMixin, TestCase):
    def test_truncated_art_download_falls_back_to_placeholder(self):
        draw = self._draw()
        Theme.objects.update(art_crop_url="https://x/art.jpg")

        def truncated(*args, **kwargs):
            response = mock.MagicMock()
            response.__enter__.return_value = response
            response.read.side_effect = http.client.IncompleteRead(b"\xff\xd8")
            return response

        with mock.patch(RECAP_URLOPEN, side_effect=truncated):
            png = ThemeDrawRecapUseCase().execute(draw)

        self.assertEqual(Image.open(io.BytesIO(png)).size, (1080, 1350))

    def test_empty_theme_and_commander_names_do_not_crash(self):
        draw = self._draw()
        Theme.objects.update(name="", top_commanders=[{"name": "", "num_decks": 1}])

        with mock.patch(RECAP_URLOPEN, side_effect=urllib.error.URLError("down")):
            png = ThemeDrawRecapUseCase().execute(draw)

        self.assertEqual(Image.open(io.BytesIO(png)).size, (1080, 1350))
