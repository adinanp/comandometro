import json
import urllib.error
from unittest import mock

from django.test import TestCase

from apps.cards.models import Theme
from apps.cards.use_cases import ResolveCommanderArtUseCase


class ThemeModelTests(TestCase):
    def test_display_num_decks_thousands(self):
        self.assertEqual(Theme(num_decks=62437).display_num_decks(), "62,4 mil decks")
        self.assertEqual(Theme(num_decks=168250).display_num_decks(), "168,3 mil decks")

    def test_display_num_decks_round_thousand(self):
        self.assertEqual(Theme(num_decks=5000).display_num_decks(), "5 mil decks")

    def test_display_num_decks_below_thousand(self):
        self.assertEqual(Theme(num_decks=7).display_num_decks(), "7 decks")
        self.assertEqual(Theme(num_decks=1).display_num_decks(), "1 deck")

    def test_top_commander_names_limits_and_handles_empty(self):
        theme = Theme(
            top_commanders=[
                {"name": "A", "num_decks": 4},
                {"name": "B", "num_decks": 3},
                {"name": "C", "num_decks": 2},
                {"name": "D", "num_decks": 1},
            ]
        )
        self.assertEqual(theme.top_commander_names(), ["A", "B", "C"])
        self.assertEqual(Theme(top_commanders=[]).top_commander_names(), [])


class _FakeResponse:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


URLOPEN = "apps.cards.use_cases.commander_art.urllib.request.urlopen"


class CommanderArtTests(TestCase):
    def test_uses_first_card_of_partner_pair(self):
        with mock.patch(URLOPEN, return_value=_FakeResponse({})) as urlopen:
            ResolveCommanderArtUseCase().execute(
                "Frodo, Adventurous Hobbit // Sam, Loyal Attendant"
            )

        url = urlopen.call_args.args[0].full_url
        self.assertIn("exact=Frodo%2C+Adventurous+Hobbit", url)
        self.assertNotIn("Sam", url)

    def test_returns_art_crop_from_image_uris(self):
        payload = {"image_uris": {"art_crop": "https://x/a.jpg"}}
        with mock.patch(URLOPEN, return_value=_FakeResponse(payload)):
            self.assertEqual(
                ResolveCommanderArtUseCase().execute("Teysa Karlov"), "https://x/a.jpg"
            )

    def test_falls_back_to_first_face(self):
        payload = {"card_faces": [{"image_uris": {"art_crop": "https://x/face.jpg"}}, {}]}
        with mock.patch(URLOPEN, return_value=_FakeResponse(payload)):
            self.assertEqual(
                ResolveCommanderArtUseCase().execute("Esika, God of the Tree"),
                "https://x/face.jpg",
            )

    def test_network_error_returns_none(self):
        with mock.patch(URLOPEN, side_effect=urllib.error.URLError("down")):
            self.assertIsNone(ResolveCommanderArtUseCase().execute("Teysa Karlov"))
