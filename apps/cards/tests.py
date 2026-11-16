import json
import urllib.error
from unittest import mock

from django.test import TestCase

from apps.cards.edhrec import EdhrecError, ThemeListing
from apps.cards.models import Theme
from apps.cards.use_cases import ResolveCommanderArtUseCase, SyncEdhrecThemesUseCase


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


class _FakeEdhrecClient:
    def __init__(self, themes, commanders, failing=()):
        self.themes = themes
        self.commanders = commanders
        self.failing = set(failing)
        self.detail_calls = []

    def list_themes(self):
        return self.themes

    def top_commanders(self, slug, limit=10):
        self.detail_calls.append(slug)
        if slug in self.failing:
            raise EdhrecError(f"falhou {slug}")
        return self.commanders.get(slug, [])


ART = "apps.cards.use_cases.sync_themes.ResolveCommanderArtUseCase.perform_request"


class SyncThemesTests(TestCase):
    def setUp(self):
        self.listing = [
            ThemeListing("voltron", "Voltron", 62437, 1),
            ThemeListing("elves", "Elves", 15700, 2),
        ]
        self.commanders = {
            "voltron": [{"name": "Cloud, Ex-SOLDIER", "num_decks": 1897}],
            "elves": [{"name": "Lathril, Blade of the Elves", "num_decks": 3676}],
        }

    def _sync(self, client, **kwargs):
        with mock.patch(ART, return_value="https://x/art.jpg"):
            return SyncEdhrecThemesUseCase().execute(client=client, delay=0, **kwargs)

    def test_upserts_catalog_and_details(self):
        result = self._sync(_FakeEdhrecClient(self.listing, self.commanders))

        self.assertEqual(result, {"themes": 2, "ok": 2, "failed": []})
        voltron = Theme.objects.get(slug="voltron")
        self.assertEqual(voltron.name, "Voltron")
        self.assertEqual(voltron.num_decks, 62437)
        self.assertEqual(voltron.popularity_rank, 1)
        self.assertEqual(voltron.top_commander_names(), ["Cloud, Ex-SOLDIER"])
        self.assertEqual(voltron.art_crop_url, "https://x/art.jpg")
        self.assertIsNotNone(voltron.edhrec_synced_at)

        self.listing[0] = ThemeListing("voltron", "Voltron", 70000, 1)
        self._sync(_FakeEdhrecClient(self.listing, self.commanders))
        self.assertEqual(Theme.objects.count(), 2)
        self.assertEqual(Theme.objects.get(slug="voltron").num_decks, 70000)

    def test_failed_detail_is_reported_and_others_continue(self):
        Theme.objects.create(
            slug="voltron", name="Voltron", top_commanders=[{"name": "Old", "num_decks": 1}]
        )

        result = self._sync(
            _FakeEdhrecClient(self.listing, self.commanders, failing={"voltron"})
        )

        self.assertEqual(result["failed"], ["voltron"])
        self.assertEqual(result["ok"], 1)
        self.assertEqual(Theme.objects.get(slug="voltron").top_commander_names(), ["Old"])
        self.assertEqual(
            Theme.objects.get(slug="elves").top_commander_names(),
            ["Lathril, Blade of the Elves"],
        )

    def test_theme_missing_from_catalog_is_kept(self):
        Theme.objects.create(slug="loci", name="Loci")

        self._sync(_FakeEdhrecClient(self.listing, self.commanders))

        self.assertTrue(Theme.objects.filter(slug="loci").exists())

    def test_only_syncs_single_slug_details(self):
        client = _FakeEdhrecClient(self.listing, self.commanders)

        self._sync(client, only="voltron")

        self.assertEqual(client.detail_calls, ["voltron"])

    def test_does_not_touch_summary(self):
        Theme.objects.create(slug="voltron", name="Voltron", summary="Já existe.")

        self._sync(_FakeEdhrecClient(self.listing, self.commanders))

        self.assertEqual(Theme.objects.get(slug="voltron").summary, "Já existe.")
