from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.core.models import Game, GameParticipant, Player
from apps.core.use_cases import DashboardStatsUseCase
from apps.pods.models import Membership, Pod


class _PodFixtureMixin:
    def setUp(self):
        self.pod = Pod.objects.create(name="Pod de Teste")
        self.ana = Player.objects.create(pod=self.pod, name="Ana")
        self.bia = Player.objects.create(pod=self.pod, name="Bia")
        self.caio = Player.objects.create(pod=self.pod, name="Caio")
        self.duda = Player.objects.create(pod=self.pod, name="Duda")

    def _game(self, placements, first_blood=None, day=1):
        game = Game.objects.create(
            pod=self.pod, date=date(2026, 10, day), first_blood_player=first_blood
        )
        for player, placement in placements.items():
            GameParticipant.objects.create(game=game, player=player, placement=placement)
        return game


class FirstBloodStatsTests(_PodFixtureMixin, TestCase):
    def test_top_first_blood_is_player_with_most_first_bloods(self):
        table = {self.ana: 1, self.bia: 2, self.caio: 3, self.duda: 4}
        self._game(table, first_blood=self.bia, day=1)
        self._game(table, first_blood=self.bia, day=2)
        self._game(table, first_blood=self.ana, day=3)

        top = DashboardStatsUseCase().execute(self.pod)["top_first_blood"]

        self.assertEqual(top["player_id"], self.bia.id)
        self.assertEqual(top["count"], 2)
        # Bia jogou 3 partidas e deu first blood em 2.
        self.assertEqual(top["percentage"], 66.7)

    def test_top_first_blood_is_none_without_any_first_blood(self):
        self._game({self.ana: 1, self.bia: 2})

        self.assertIsNone(DashboardStatsUseCase().execute(self.pod)["top_first_blood"])


class FirstToDieStatsTests(_PodFixtureMixin, TestCase):
    def test_first_to_die_is_player_with_worst_placement_most_often(self):
        self._game({self.ana: 1, self.bia: 2, self.caio: 3, self.duda: 4}, day=1)
        self._game({self.ana: 1, self.bia: 2, self.caio: 4, self.duda: 3}, day=2)
        self._game({self.ana: 2, self.bia: 1, self.caio: 3, self.duda: 4}, day=3)

        top = DashboardStatsUseCase().execute(self.pod)["top_first_to_die"]

        self.assertEqual(top["player_id"], self.duda.id)
        self.assertEqual(top["count"], 2)
        self.assertEqual(top["percentage"], 66.7)

    def test_games_with_missing_placement_are_ignored(self):
        self._game({self.ana: 1, self.bia: 2, self.caio: None})

        self.assertIsNone(DashboardStatsUseCase().execute(self.pod)["top_first_to_die"])

    def test_tied_worst_placement_counts_for_everyone_tied(self):
        self._game({self.ana: 1, self.bia: 2, self.caio: 3, self.duda: 3}, day=1)
        self._game({self.ana: 1, self.bia: 2, self.caio: 3, self.duda: 4}, day=2)

        top = DashboardStatsUseCase().execute(self.pod)["top_first_to_die"]

        self.assertEqual(top["player_id"], self.duda.id)
        self.assertEqual(top["count"], 2)

    def test_games_where_all_losers_tie_are_ignored(self):
        # Só o vencedor registrado e o resto empatado: não dá pra saber quem
        # caiu primeiro, então a partida não conta pra ninguém.
        self._game({self.ana: 1, self.bia: 2, self.caio: 2, self.duda: 2}, day=1)
        self._game({self.ana: 1, self.bia: 2, self.caio: 2, self.duda: 2}, day=2)
        self._game({self.ana: 1, self.bia: 2, self.caio: 3, self.duda: 4}, day=3)

        top = DashboardStatsUseCase().execute(self.pod)["top_first_to_die"]

        self.assertEqual(top["player_id"], self.duda.id)
        self.assertEqual(top["count"], 1)


class GameFormFirstBloodTests(_PodFixtureMixin, TestCase):
    def setUp(self):
        super().setUp()
        user = get_user_model().objects.create_user("membro", password="x")
        Membership.objects.create(pod=self.pod, user=user)
        self.client.force_login(user)
        self.url = reverse("core:game-create", kwargs={"pod_slug": self.pod.slug})

    def _post(self, first_blood):
        data = {
            "date": "2026-10-01",
            "win_condition": "Combo",
            "first_blood_player": first_blood.id if first_blood else "",
            "form-TOTAL_FORMS": "2",
            "form-INITIAL_FORMS": "0",
            "form-MIN_NUM_FORMS": "2",
            "form-MAX_NUM_FORMS": "1000",
            "form-0-player": self.ana.id,
            "form-0-placement": "1",
            "form-1-player": self.bia.id,
            "form-1-placement": "2",
            "achievements-TOTAL_FORMS": "0",
            "achievements-INITIAL_FORMS": "0",
            "achievements-MIN_NUM_FORMS": "0",
            "achievements-MAX_NUM_FORMS": "1000",
        }
        return self.client.post(self.url, data)

    def test_saves_first_blood_player(self):
        response = self._post(self.ana)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(Game.objects.get().first_blood_player, self.ana)

    def test_rejects_first_blood_player_who_did_not_play(self):
        response = self._post(self.caio)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(Game.objects.exists())
