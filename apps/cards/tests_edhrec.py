import http.client
import json
import urllib.error
from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase

from apps.cards.edhrec import EdhrecError, EdhrecThemeClient, ThemeListing

TEST_DATA = Path(__file__).parent / "test_data"


def _load(name):
    return json.loads((TEST_DATA / name).read_text(encoding="utf-8"))


class EdhrecParsingTests(SimpleTestCase):
    def test_parse_theme_list(self):
        # O catálogo traz a contagem em `num_decks`; o campo `slug` do item é
        # o de uma carta ilustrativa, então o slug do tema vem do `url`.
        themes = EdhrecThemeClient.parse_theme_list(_load("edhrec_tags.json"))

        self.assertEqual(
            themes,
            [
                ThemeListing("tokens", "Tokens", 208942, 1),
                ThemeListing("plus-1-plus-1-counters", "+1/+1 Counters", 168250, 2),
                ThemeListing("combo", "Combo", 123806, 3),
            ],
        )

    def test_parse_top_commanders_uses_topcommanders_list_in_order(self):
        payload = _load("edhrec_tag_voltron.json")

        commanders = EdhrecThemeClient.parse_top_commanders(payload, limit=10)

        self.assertEqual(
            [c["name"] for c in commanders],
            [
                "Cloud, Ex-SOLDIER",
                "Kotis, the Fangkeeper",
                "Light-Paws, Emperor's Voice",
                "Captain America, First Avenger",
            ],
        )
        self.assertEqual(commanders[0]["num_decks"], 1897)
        self.assertEqual(len(EdhrecThemeClient.parse_top_commanders(payload, limit=2)), 2)

    def test_parse_top_commanders_missing_list_returns_empty(self):
        payload = {"container": {"json_dict": {"cardlists": [{"tag": "topcards", "cardviews": []}]}}}

        self.assertEqual(EdhrecThemeClient.parse_top_commanders(payload, limit=10), [])

    def test_list_themes_wraps_network_error(self):
        with mock.patch(
            "apps.cards.edhrec.urllib.request.urlopen",
            side_effect=urllib.error.URLError("down"),
        ):
            with self.assertRaises(EdhrecError):
                EdhrecThemeClient().list_themes()


class EdhrecRobustnessTests(SimpleTestCase):
    def test_truncated_body_is_wrapped_as_edhrec_error(self):
        response = mock.MagicMock()
        response.__enter__.return_value = response
        response.read.side_effect = http.client.IncompleteRead(b"{")
        with mock.patch("apps.cards.edhrec.urllib.request.urlopen", return_value=response):
            with self.assertRaises(EdhrecError):
                EdhrecThemeClient().top_commanders("voltron")

    def test_commander_without_name_is_skipped(self):
        payload = {
            "container": {
                "json_dict": {
                    "cardlists": [
                        {
                            "tag": "topcommanders",
                            "cardviews": [{"num_decks": 3}, {"name": "Teysa Karlov", "num_decks": 2}],
                        }
                    ]
                }
            }
        }

        commanders = EdhrecThemeClient.parse_top_commanders(payload, limit=10)

        self.assertEqual(commanders, [{"name": "Teysa Karlov", "num_decks": 2}])
