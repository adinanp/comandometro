from django.test import TestCase

from apps.cards.models import Theme


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
