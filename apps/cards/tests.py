import json
import urllib.error
from unittest import mock

from django.test import TestCase, override_settings

from apps.cards.edhrec import EdhrecError, ThemeListing
from apps.cards.llm import LlmError
from apps.cards.models import Theme
from apps.cards.use_cases import (
    EnsureThemeSummaryUseCase,
    ResolveCommanderArtUseCase,
    SyncEdhrecThemesUseCase,
)
from apps.cards.use_cases.theme_summary import build_summary_prompt, clean_summary


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


GENERATE = "apps.cards.use_cases.theme_summary.generate_text"


@override_settings(GEMINI_API_KEY="k", GEMINI_MODEL="modelo-teste")
class ThemeSummaryTests(TestCase):
    def setUp(self):
        self.theme = Theme.objects.create(
            slug="aristocrats",
            name="Aristocrats",
            top_commanders=[
                {"name": "Teysa Karlov", "num_decks": 3191},
                {"name": "Sephiroth, Fabled SOLDIER", "num_decks": 2690},
                {"name": "Meren of Clan Nel Toth", "num_decks": 1618},
                {"name": "Quarto Comandante", "num_decks": 10},
            ],
        )

    def test_returns_cached_summary_without_calling_llm(self):
        self.theme.summary = "Já existe."
        self.theme.save()

        with mock.patch(GENERATE) as generate:
            self.assertEqual(EnsureThemeSummaryUseCase().execute(self.theme), "Já existe.")
        generate.assert_not_called()

    @override_settings(GEMINI_API_KEY="")
    def test_no_api_key_returns_none_without_calling_llm(self):
        with mock.patch(GENERATE) as generate:
            self.assertIsNone(EnsureThemeSummaryUseCase().execute(self.theme))
        generate.assert_not_called()

    def test_saves_summary_model_and_timestamp(self):
        with mock.patch(GENERATE, return_value="Sacrifica criaturas por valor."):
            summary = EnsureThemeSummaryUseCase().execute(self.theme)

        self.assertEqual(summary, "Sacrifica criaturas por valor.")
        self.theme.refresh_from_db()
        self.assertEqual(self.theme.summary, "Sacrifica criaturas por valor.")
        self.assertEqual(self.theme.summary_model, "modelo-teste")
        self.assertIsNotNone(self.theme.summary_generated_at)

    def test_llm_error_returns_none_and_saves_nothing(self):
        with mock.patch(GENERATE, side_effect=LlmError("cota")):
            self.assertIsNone(EnsureThemeSummaryUseCase().execute(self.theme))

        self.theme.refresh_from_db()
        self.assertEqual(self.theme.summary, "")
        self.assertIsNone(self.theme.summary_generated_at)

    def test_empty_llm_response_returns_none(self):
        with mock.patch(GENERATE, return_value="   "):
            self.assertIsNone(EnsureThemeSummaryUseCase().execute(self.theme))

        self.theme.refresh_from_db()
        self.assertEqual(self.theme.summary, "")

    def test_clean_summary_strips_noise(self):
        self.assertEqual(
            clean_summary('"Resumo: Sacrifica criaturas\npor valor."'),
            "Sacrifica criaturas por valor.",
        )
        self.assertEqual(
            clean_summary("“Sacrifica criaturas por valor.”"),
            "Sacrifica criaturas por valor.",
        )

    def test_clean_summary_truncates_on_word_boundary(self):
        words = ["palavra"] * 30  # 239 caracteres
        raw = " ".join(words)

        cleaned = clean_summary(raw)

        self.assertLessEqual(len(cleaned), 120)
        self.assertTrue(cleaned.endswith("…"))
        self.assertTrue(all(w == "palavra" for w in cleaned[:-1].split(" ")))

    def test_prompt_is_grounded(self):
        prompt = build_summary_prompt(self.theme)

        self.assertIn("Aristocrats", prompt)
        for name in ("Teysa Karlov", "Sephiroth, Fabled SOLDIER", "Meren of Clan Nel Toth"):
            self.assertIn(name, prompt)
        self.assertIn("120", prompt)
        self.assertIn("português", prompt)


class SyncThemesRobustnessTests(SyncThemesTests):
    def test_unexpected_error_in_one_theme_does_not_abort_sync(self):
        client = _FakeEdhrecClient(self.listing, self.commanders)
        original = client.top_commanders

        def flaky(slug, limit=10):
            if slug == "voltron":
                raise KeyError("name")
            return original(slug, limit)

        client.top_commanders = flaky

        result = self._sync(client)

        self.assertEqual(result["failed"], ["voltron"])
        self.assertEqual(result["ok"], 1)


class CleanSummaryEdgeCaseTests(TestCase):
    def test_keeps_only_first_paragraph_and_strips_inner_quotes(self):
        self.assertEqual(
            clean_summary("\"'Resumo: ok'\n\nNota: extra"),
            "ok",
        )

    def test_strips_markdown_emphasis_and_prefix(self):
        self.assertEqual(clean_summary("**Resumo:** _Sacrifica_ criaturas."), "Sacrifica criaturas.")


class ThemeEdhrecUrlTests(TestCase):
    def test_edhrec_url_points_to_tag_page(self):
        self.assertEqual(
            Theme(slug="plus-1-plus-1-counters").edhrec_url,
            "https://edhrec.com/tags/plus-1-plus-1-counters",
        )
