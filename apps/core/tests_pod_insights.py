from datetime import date

from django.test import TestCase

from apps.core.models import Deck, Game, GameParticipant, Player
from apps.core.use_cases import PodInsightsUseCase
from apps.pods.models import Pod


class PodInsightsUseCaseTests(TestCase):
    """
    Ana (WU) joga 6 partidas contra Bia (B) em outubro e ganha 4. Em
    setembro, outro deck da Ana (WU) ganha do deck colorless da Bia. Caio
    não jogou nada.
    """

    def setUp(self):
        self.pod = Pod.objects.create(name="Pod de Teste")
        self.ana = Player.objects.create(pod=self.pod, name="Ana")
        self.bia = Player.objects.create(pod=self.pod, name="Bia")
        self.caio = Player.objects.create(pod=self.pod, name="Caio")
        self.ana_main = self._deck(self.ana, "WU")
        self.ana_alt = self._deck(self.ana, "WU")
        self.bia_main = self._deck(self.bia, "B")
        self.bia_alt = self._deck(self.bia, "C")

        for day in range(1, 7):
            ana_won = day <= 4
            self._game(
                date(2026, 10, day),
                (self.ana, self.ana_main, 1 if ana_won else 2),
                (self.bia, self.bia_main, 2 if ana_won else 1),
            )
        self._game(
            date(2026, 9, 20),
            (self.ana, self.ana_alt, 1),
            (self.bia, self.bia_alt, 2),
        )

    def _deck(self, player, identity):
        deck = Deck.objects.create(player=player)
        Deck.objects.filter(pk=deck.pk).update(color_identity=identity)
        return deck

    def _game(self, game_date, *seats):
        game = Game.objects.create(pod=self.pod, date=game_date)
        for player, deck, placement in seats:
            GameParticipant.objects.create(
                game=game, player=player, deck=deck, placement=placement
            )

    def _summary(self, rows, *keys):
        return [
            {"empty": True} if row.get("empty") else {key: row[key] for key in keys}
            for row in rows
        ]

    def test_color_identity_stats_group_by_exact_combo(self):
        insights = PodInsightsUseCase().execute(self.pod)

        self.assertEqual(
            self._summary(insights["color_identity_stats"], "identity", "games", "wins", "win_rate"),
            [
                {"identity": "WU", "games": 7, "wins": 5, "win_rate": 71.4},
                {"identity": "B", "games": 6, "wins": 2, "win_rate": 33.3},
                {"identity": "C", "games": 1, "wins": 0, "win_rate": 0.0},
                {"empty": True},
                {"empty": True},
            ],
        )

    def test_top_commanders_require_minimum_games(self):
        insights = PodInsightsUseCase().execute(self.pod)

        rows = insights["top_commanders"]
        self.assertEqual(
            [(row["deck"], row["player"], row["games"], row["wins"], row["win_rate"]) for row in rows[:2]],
            [
                (self.ana_main, self.ana, 6, 4, 66.7),
                (self.bia_main, self.bia, 6, 2, 33.3),
            ],
        )
        self.assertEqual(rows[2:], [{"empty": True}] * 3)

    def test_points_ranking_includes_players_without_games(self):
        insights = PodInsightsUseCase().execute(self.pod)

        self.assertEqual(
            [(row["player"], row["points"]) for row in insights["points_ranking"]],
            [(self.ana, 24), (self.bia, 18), (self.caio, 0)],
        )

    def test_since_filters_every_section(self):
        insights = PodInsightsUseCase().execute(self.pod, since=date(2026, 10, 1))

        self.assertEqual(
            self._summary(insights["color_identity_stats"], "identity", "games", "wins")[:3],
            [
                {"identity": "WU", "games": 6, "wins": 4},
                {"identity": "B", "games": 6, "wins": 2},
                {"empty": True},
            ],
        )
        self.assertEqual(
            [(row["player"], row["points"]) for row in insights["points_ranking"]],
            [(self.ana, 20), (self.bia, 16), (self.caio, 0)],
        )
        self.assertEqual(
            [row["games"] for row in insights["top_commanders"][:2]], [6, 6]
        )

    def test_query_count_does_not_grow_with_decks(self):
        """O banco fica em outra nuvem (Neon), cada query custa dezenas de ms:
        o número de queries não pode crescer com a quantidade de decks."""
        for index in range(20):
            self._deck(self.caio, "R" if index % 2 else "G")

        with self.assertNumQueries(5):
            PodInsightsUseCase().execute(self.pod)
