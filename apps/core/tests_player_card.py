from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.cards.edhrec import EdhrecError
from apps.cards.models import Card
from apps.core.models import Deck, Player
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
