from datetime import datetime, timedelta
from datetime import timezone as dt_timezone
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.cards.edhrec import EdhrecError
from apps.cards.models import Card, Theme
from apps.core.models import Deck, Player, PlayerWeeklyTheme
from apps.core.use_cases import EnsureWeeklyThemeUseCase, RerollWeeklyThemeUseCase
from apps.core.use_cases.draw_themes import week_start
from apps.core.use_cases.weekly_theme import eligible_weekly_themes
from apps.pods.models import Membership, Pod

COMMANDER_SLUGS = "apps.cards.edhrec.EdhrecThemeClient.commander_theme_slugs"


class PlayerCardFixtureMixin:
    def setUp(self):
        self.pod = Pod.objects.create(name="Pod de Teste")
        self.user = get_user_model().objects.create_user(username="ana", password="x")
        Membership.objects.create(pod=self.pod, user=self.user)
        self.player = Player.objects.create(pod=self.pod, name="Ana", user=self.user)
        self.client.force_login(self.user)


class DeckCreateCommanderThemesTests(PlayerCardFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        self.teysa = Card.objects.create(name="Teysa Karlov", is_commander_eligible=True)

    def _post(self, url_name):
        url = reverse(f"core:{url_name}", kwargs={"pod_slug": self.pod.slug})
        data = {"player": self.player.pk, "is_active": "on", "commander_1": self.teysa.pk}
        if url_name == "deck-create-ajax":
            data = {f"new_deck-{key}": value for key, value in data.items()}
        return self.client.post(url, data)

    def test_creating_deck_fetches_missing_commander_themes(self):
        for url_name in ("deck-create", "deck-create-ajax"):
            with self.subTest(url_name):
                Deck.objects.all().delete()
                Card.objects.filter(pk=self.teysa.pk).update(
                    edhrec_theme_slugs=[], edhrec_themes_synced_at=None
                )
                with mock.patch(COMMANDER_SLUGS, return_value=["aristocrats"]):
                    response = self._post(url_name)

                self.assertLess(response.status_code, 400)
                self.teysa.refresh_from_db()
                self.assertEqual(self.teysa.edhrec_theme_slugs, ["aristocrats"])

    def test_creating_deck_skips_commanders_already_synced(self):
        for url_name in ("deck-create", "deck-create-ajax"):
            with self.subTest(url_name):
                Deck.objects.all().delete()
                Card.objects.filter(pk=self.teysa.pk).update(
                    edhrec_themes_synced_at="2026-11-01T00:00:00Z"
                )
                with mock.patch(COMMANDER_SLUGS) as fetch:
                    self._post(url_name)

                fetch.assert_not_called()

    def test_edhrec_down_still_creates_deck(self):
        for url_name in ("deck-create", "deck-create-ajax"):
            with self.subTest(url_name):
                Deck.objects.all().delete()
                Card.objects.filter(pk=self.teysa.pk).update(edhrec_themes_synced_at=None)
                with mock.patch(COMMANDER_SLUGS, side_effect=EdhrecError("fora do ar")):
                    response = self._post(url_name)

                self.assertLess(response.status_code, 400)
                self.assertEqual(Deck.objects.filter(player=self.player).count(), 1)
                self.teysa.refresh_from_db()
                self.assertIsNone(self.teysa.edhrec_themes_synced_at)


SUNDAY_NIGHT = datetime(2026, 11, 16, 2, 30, tzinfo=dt_timezone.utc)  # dom 23:30 SP
MONDAY_EARLY = datetime(2026, 11, 16, 3, 30, tzinfo=dt_timezone.utc)  # seg 00:30 SP


class WeeklyThemeTests(PlayerCardFixtureMixin, TestCase):
    def _themes(self, count, prefix="tema"):
        return [
            Theme.objects.create(slug=f"{prefix}-{i}", name=f"Tema {i}", popularity_rank=i)
            for i in range(count)
        ]

    def _comfort(self, slugs):
        card = Card.objects.create(
            name=f"Comandante {Card.objects.count()}",
            is_commander_eligible=True,
            edhrec_theme_slugs=list(slugs),
        )
        deck = Deck.objects.create(player=self.player)
        deck.commanders.set([card])

    def _rows(self, now=MONDAY_EARLY):
        return PlayerWeeklyTheme.objects.filter(
            player=self.player, week_start=week_start(now).date()
        )

    def test_never_draws_comfort_zone_theme(self):
        themes = self._themes(10)
        self._comfort([t.slug for t in themes[:9]])

        result = EnsureWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)

        self.assertEqual(result["theme"], themes[9])
        self.assertEqual(result["rerolls_left"], 2)

    def test_deck_without_commander_data_does_not_break(self):
        self._themes(3)
        self._comfort([])

        self.assertIsNotNone(EnsureWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY))

    def test_first_visit_creates_one_row_second_does_not(self):
        self._themes(5)

        first = EnsureWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)
        second = EnsureWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)

        self.assertEqual(self._rows().count(), 1)
        self.assertEqual(first["theme"], second["theme"])

    def test_excludes_themes_from_last_four_weeks(self):
        themes = self._themes(5)
        this_week = week_start(MONDAY_EARLY).date()
        for weeks_ago, theme in zip((1, 2, 3, 4), themes):
            PlayerWeeklyTheme.objects.create(
                player=self.player, theme=theme, week_start=this_week - timedelta(weeks=weeks_ago)
            )

        eligible = set(eligible_weekly_themes(self.player, this_week))

        self.assertEqual(eligible, {themes[3], themes[4]})  # 4 semanas atrás volta a valer

    def test_reroll_twice_then_blocked(self):
        self._themes(10)
        EnsureWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)

        first = RerollWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)
        second = RerollWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)

        self.assertEqual((first["rerolls_left"], second["rerolls_left"]), (1, 0))
        self.assertEqual(self._rows().values("theme").distinct().count(), 3)
        with self.assertRaises(ValidationError):
            RerollWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)
        self.assertEqual(self._rows().count(), 3)

    def test_reroll_never_repeats_this_week(self):
        themes = self._themes(7)
        self._comfort([t.slug for t in themes[:3]])
        EnsureWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)
        RerollWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)
        RerollWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)

        drawn = list(self._rows().values_list("theme_id", flat=True))
        self.assertEqual(len(set(drawn)), 3)
        self.assertFalse(set(drawn) & {t.id for t in themes[:3]})

    def test_week_boundary_sao_paulo_resets_rerolls(self):
        self._themes(10)
        EnsureWeeklyThemeUseCase().execute(self.player, now=SUNDAY_NIGHT)
        RerollWeeklyThemeUseCase().execute(self.player, now=SUNDAY_NIGHT)
        RerollWeeklyThemeUseCase().execute(self.player, now=SUNDAY_NIGHT)

        monday = EnsureWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)

        self.assertEqual(monday["rerolls_left"], 2)
        self.assertEqual(self._rows(SUNDAY_NIGHT).count(), 3)
        self.assertEqual(self._rows(MONDAY_EARLY).count(), 1)

    def test_reroll_without_row_acts_as_first_draw(self):
        self._themes(5)

        result = RerollWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)

        self.assertEqual(result["rerolls_left"], 2)
        self.assertEqual(self._rows().count(), 1)

    def test_relaxes_rules_when_nothing_eligible(self):
        themes = self._themes(2)
        self._comfort([t.slug for t in themes])  # tudo na zona de conforto
        PlayerWeeklyTheme.objects.create(
            player=self.player,
            theme=themes[0],
            week_start=week_start(MONDAY_EARLY).date() - timedelta(weeks=1),
        )

        first = EnsureWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)
        self.assertIn(first["theme"], themes)

        second = RerollWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)
        self.assertNotEqual(second["theme"], first["theme"])

        # Os 2 temas já saíram nesta semana: não há troca possível e nada é gasto.
        self.assertIsNone(RerollWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY))
        self.assertEqual(self._rows().count(), 2)
        current = EnsureWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY)
        self.assertEqual(current["theme"], second["theme"])
        self.assertEqual(current["rerolls_left"], 1)

    def test_empty_catalog_returns_none(self):
        self.assertIsNone(EnsureWeeklyThemeUseCase().execute(self.player, now=MONDAY_EARLY))
        self.assertEqual(self._rows().count(), 0)
