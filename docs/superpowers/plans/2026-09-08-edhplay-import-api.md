# EDHPlay Import API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pod-scoped API endpoint to Comandometro that accepts the
JSON produced by the EDHPlay Match Logger browser extension (wrapped with
an explicit seat→Player/Deck mapping) and creates the corresponding `Game`
and `GameParticipant` records.

**Architecture:** One new Django class-based view (`GameImportView`),
following the existing `apps/core/views/*.py` + `JsonResponse` conventions
already used elsewhere in this app (no DRF in this project). Authenticated
by a static bearer token from an environment variable — not a Django
session — since it's called manually via curl/httpie, not from a browser.
Validation and creation are two clearly separated methods on the same view,
both covered by `django.test.TestCase` (the only test style already used in
this repo).

**Tech Stack:** Django (existing stack — no new dependencies).

## Global Constraints

- The endpoint is authenticated by a static token from the
  `IMPORT_API_TOKEN` environment variable, checked via an `Authorization:
  Bearer <token>` header — no session/CSRF involved.
- The request body wraps the extension's JSON (`match`, unmodified schema
  v1) with an explicit `seat_mappings` array (`{seat, player_id, deck_id}`)
  — there is no fuzzy name-matching of `display_name` to `Player` on the
  server. Every seat in `match.seats` must have a corresponding mapping, or
  the request is rejected with `400`.
- `deck_id` is optional per seat mapping; when absent, `GameParticipant.deck`
  is `None`, exactly like the existing manual `GameForm` flow.
- `player_id`/`deck_id` are validated against the pod resolved from the URL
  (`pod_slug`) — a player from another pod, or a deck belonging to a
  different player than the one mapped to that seat, is a `400`, not a
  silently-wrong association.
- Game + all its participants are created inside one
  `transaction.atomic()` block — a validation failure creates nothing, and
  there's no separate "create then fix up" step.
- An unresolved `mvp_card` name (no matching `Card.name`, case-insensitive)
  is a **warning** returned in the response, not a request failure — the
  rest of the import still goes through.
- No web UI, no DRF, no new database models — the existing `Game` /
  `GameParticipant` fields already cover what this endpoint writes (see
  the design spec: `docs/superpowers/specs/2026-09-08-edhplay-match-capture-design.md`).

---

### Task 1: Auth gate, pod resolution, and URL wiring

**Files:**
- Create: `apps/core/views/game_import.py`
- Modify: `apps/core/views/__init__.py`
- Modify: `apps/core/urls.py`
- Modify: `config/settings/base.py`
- Modify: `.env.example`
- Modify: `apps/core/tests.py`

**Interfaces:**
- Produces: `GameImportView` (a `django.views.View` subclass), URL name
  `core:game-import` resolving to `/p/<pod_slug>/partidas/importar/`.
  `self.pod` (a `Pod` instance) is set in `dispatch()` for later tasks to
  use. `settings.IMPORT_API_TOKEN` (string, default `""`).

- [ ] **Step 1: Write the failing tests**

Replace the contents of `apps/core/tests.py` (currently just the default
`TestCase` stub) with:

```python
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.pods.models import Pod


@override_settings(IMPORT_API_TOKEN="test-token")
class GameImportAuthTests(TestCase):
    def setUp(self):
        self.pod = Pod.objects.create(name="Pod de Teste")
        self.url = reverse("core:game-import", kwargs={"pod_slug": self.pod.slug})

    def test_rejects_request_without_authorization_header(self):
        response = self.client.post(self.url, data="{}", content_type="application/json")
        self.assertEqual(response.status_code, 401)

    def test_rejects_request_with_wrong_token(self):
        response = self.client.post(
            self.url,
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer wrong-token",
        )
        self.assertEqual(response.status_code, 401)

    def test_returns_404_for_unknown_pod_slug(self):
        url = reverse("core:game-import", kwargs={"pod_slug": "nao-existe"})
        response = self.client.post(
            url,
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(response.status_code, 404)

    def test_accepts_request_with_correct_token(self):
        response = self.client.post(
            self.url,
            data="{}",
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(response.status_code, 200)

    def test_rejects_invalid_json_body(self):
        response = self.client.post(
            self.url,
            data="not-json",
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )
        self.assertEqual(response.status_code, 400)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.core.tests.GameImportAuthTests`
Expected: FAIL (`NoReverseMatch: 'game-import' is not a registered
namespace/URL name` or similar — nothing exists yet).

- [ ] **Step 3: Add the setting, the view, and the URL**

Add to `config/settings/base.py`, right after `ADMIN_ENABLED` (around line
47):
```python
# Token estático pra autenticar POST /p/<pod_slug>/partidas/importar/ — ver
# docs/superpowers/specs/2026-09-08-edhplay-match-capture-design.md. Chamado
# manualmente (curl/httpie), nunca pelo navegador — por isso token e não
# sessão/CSRF.
IMPORT_API_TOKEN = env("IMPORT_API_TOKEN", default="")
```

Add to `.env.example`, after `GOOGLE_CLIENT_SECRET=`:
```
IMPORT_API_TOKEN=
```

Create `apps/core/views/game_import.py`:
```python
import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.pods.models import Pod


class GameImportView(View):
    """
    Recebe o JSON exportado pela extensão EDHPlay Match Logger (embrulhado
    com um mapeamento explícito assento -> Player/Deck) e cria a partida
    correspondente neste pod. Autenticado por token estático — pensado pra
    ser chamado manualmente via curl/httpie, não pelo navegador. Ver
    docs/superpowers/specs/2026-09-08-edhplay-match-capture-design.md.
    """

    def dispatch(self, request, *args, **kwargs):
        expected_token = settings.IMPORT_API_TOKEN
        auth_header = request.headers.get("Authorization", "")
        if not expected_token or auth_header != f"Bearer {expected_token}":
            return JsonResponse({"error": "unauthorized"}, status=401)
        self.pod = get_object_or_404(Pod, slug=kwargs["pod_slug"])
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            json.loads(request.body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"errors": ["Corpo da requisição não é um JSON válido."]}, status=400)
        return JsonResponse({"status": "authorized", "pod": self.pod.slug}, status=200)
```

Update `apps/core/views/__init__.py` — add the import and export:
```python
from .dashboard import DashboardView
from .player_profile import PlayerProfileView
from .player_list import PlayerListView
from .my_profile import MyProfileView
from .my_decks import MyDecksView, DeckDeleteView
from .game_list import GameListView
from .game_detail import GameDetailView
from .game_create import GameCreateView
from .game_update import GameUpdateView
from .game_import import GameImportView
from .deck_detail import DeckDetailView
from .deck_create import DeckCreateView
from .deck_create_ajax import DeckCreateAjaxView
from .deck_list import DeckListView
from .deck_decklist import DeckDecklistView

__all__ = [
    "DashboardView",
    "PlayerProfileView",
    "PlayerListView",
    "MyProfileView",
    "MyDecksView",
    "DeckDeleteView",
    "GameListView",
    "GameDetailView",
    "GameCreateView",
    "GameUpdateView",
    "GameImportView",
    "DeckDetailView",
    "DeckCreateView",
    "DeckCreateAjaxView",
    "DeckListView",
    "DeckDecklistView",
]
```

Update `apps/core/urls.py` — add `GameImportView` to the import block and a
new path right after `game-update`:
```python
from apps.core.views import (
    DashboardView,
    DeckCreateAjaxView,
    DeckCreateView,
    DeckDecklistView,
    DeckDeleteView,
    DeckDetailView,
    DeckListView,
    GameCreateView,
    GameDetailView,
    GameImportView,
    GameListView,
    GameUpdateView,
    MyDecksView,
    MyProfileView,
    PlayerListView,
    PlayerProfileView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("meu-perfil/", MyProfileView.as_view(), name="my-profile"),
    path("meus-decks/", MyDecksView.as_view(), name="my-decks"),
    path("jogadores/", PlayerListView.as_view(), name="player-list"),
    path("jogadores/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
    path("partidas/", GameListView.as_view(), name="game-list"),
    path("partidas/nova/", GameCreateView.as_view(), name="game-create"),
    path("partidas/importar/", GameImportView.as_view(), name="game-import"),
    path("partidas/<int:pk>/", GameDetailView.as_view(), name="game-detail"),
    path("partidas/<int:pk>/editar/", GameUpdateView.as_view(), name="game-update"),
    path("decks/", DeckListView.as_view(), name="deck-list"),
    path("decks/novo/", DeckCreateView.as_view(), name="deck-create"),
    path("decks/novo/ajax/", DeckCreateAjaxView.as_view(), name="deck-create-ajax"),
    path("decks/<int:pk>/", DeckDetailView.as_view(), name="deck-detail"),
    path("decks/<int:pk>/lista/", DeckDecklistView.as_view(), name="deck-decklist"),
    path("decks/<int:pk>/excluir/", DeckDeleteView.as_view(), name="deck-delete"),
]
```
(`partidas/importar/` is listed before `partidas/<int:pk>/` on purpose —
Django matches path patterns top-to-bottom, and `<int:pk>` would never let
a literal `importar` segment through if it came first.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.core.tests.GameImportAuthTests`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/core/views/game_import.py apps/core/views/__init__.py apps/core/urls.py config/settings/base.py .env.example apps/core/tests.py
git commit -m "$(cat <<'EOF'
Add token-authenticated skeleton for the EDHPlay game import endpoint

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Request validation (schema, seat mapping, pod ownership)

**Files:**
- Modify: `apps/core/views/game_import.py`
- Modify: `apps/core/tests.py`

**Interfaces:**
- Consumes: `self.pod` (set by `dispatch()` in Task 1).
- Produces: `GameImportView._validate(self, match: dict, seat_mappings:
  list) -> list[str]` (list of human-readable error messages, empty when
  valid). `post()` now calls this and returns `400` with `{"errors": [...]}`
  when non-empty.

- [ ] **Step 1: Write the failing tests**

Add to `apps/core/tests.py` (new imports at the top, new `TestCase` class
at the end):

```python
from apps.cards.models import Card
from apps.core.models import Deck, Player


@override_settings(IMPORT_API_TOKEN="test-token")
class GameImportValidationTests(TestCase):
    def setUp(self):
        self.pod = Pod.objects.create(name="Pod de Teste")
        self.other_pod = Pod.objects.create(name="Outro Pod")
        self.player1 = Player.objects.create(pod=self.pod, name="Adinan")
        self.player2 = Player.objects.create(pod=self.pod, name="Bruno")
        self.outsider = Player.objects.create(pod=self.other_pod, name="Carol")
        self.deck1 = Deck.objects.create(player=self.player1)
        self.url = reverse("core:game-import", kwargs={"pod_slug": self.pod.slug})

    def _post(self, body):
        return self.client.post(
            self.url,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

    def _valid_match(self, **overrides):
        match = {
            "schema_version": 1,
            "source": "edhplay",
            "captured_at": "2026-09-08T21:00:00Z",
            "turn_count": 7,
            "win_condition": "Dano de Comandante",
            "notes": "",
            "seats": [
                {"seat": 1, "display_name": "AdinanP", "is_winner": True, "eliminated_on_turn": None},
                {"seat": 2, "display_name": "BrunoB", "is_winner": False, "eliminated_on_turn": 5},
            ],
            "eliminations": [{"victim_seat": 2, "killer_seat": 1, "turn": 5}],
        }
        match.update(overrides)
        return match

    def test_rejects_wrong_schema_version(self):
        response = self._post(
            {
                "match": self._valid_match(schema_version=2),
                "seat_mappings": [
                    {"seat": 1, "player_id": self.player1.id},
                    {"seat": 2, "player_id": self.player2.id},
                ],
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("schema_version", response.json()["errors"][0])

    def test_rejects_missing_seat_mapping(self):
        response = self._post(
            {
                "match": self._valid_match(),
                "seat_mappings": [{"seat": 1, "player_id": self.player1.id}],
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(any("assento" in e.lower() for e in response.json()["errors"]))

    def test_rejects_player_from_another_pod(self):
        response = self._post(
            {
                "match": self._valid_match(),
                "seat_mappings": [
                    {"seat": 1, "player_id": self.player1.id},
                    {"seat": 2, "player_id": self.outsider.id},
                ],
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(any("não pertence a este pod" in e for e in response.json()["errors"]))

    def test_rejects_deck_belonging_to_a_different_player(self):
        response = self._post(
            {
                "match": self._valid_match(),
                "seat_mappings": [
                    {"seat": 1, "player_id": self.player1.id},
                    {"seat": 2, "player_id": self.player2.id, "deck_id": self.deck1.id},
                ],
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(any("não pertence ao player_id" in e for e in response.json()["errors"]))

    def test_rejects_duplicate_player_across_seats(self):
        response = self._post(
            {
                "match": self._valid_match(),
                "seat_mappings": [
                    {"seat": 1, "player_id": self.player1.id},
                    {"seat": 2, "player_id": self.player1.id},
                ],
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(any("repetido" in e for e in response.json()["errors"]))

    def test_rejects_zero_or_multiple_winners(self):
        match = self._valid_match()
        match["seats"][1]["is_winner"] = True
        response = self._post(
            {
                "match": match,
                "seat_mappings": [
                    {"seat": 1, "player_id": self.player1.id},
                    {"seat": 2, "player_id": self.player2.id},
                ],
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertTrue(any("is_winner=true" in e for e in response.json()["errors"]))

    def test_accepts_a_fully_valid_payload(self):
        response = self._post(
            {
                "match": self._valid_match(),
                "seat_mappings": [
                    {"seat": 1, "player_id": self.player1.id, "deck_id": self.deck1.id},
                    {"seat": 2, "player_id": self.player2.id},
                ],
            }
        )
        self.assertEqual(response.status_code, 200)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.core.tests.GameImportValidationTests`
Expected: FAIL — every case gets `200`/no-op from the Task 1 stub instead of
the expected `400`s (the last one, `test_accepts_a_fully_valid_payload`,
already passes — that's fine, it'll keep passing).

- [ ] **Step 3: Write the implementation**

Replace `post()` and add `_validate()` in
`apps/core/views/game_import.py` (imports grow — replace the whole file
header's import block too):

```python
import json

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.core.models import Deck, Player
from apps.pods.models import Pod


class GameImportView(View):
    """
    Recebe o JSON exportado pela extensão EDHPlay Match Logger (embrulhado
    com um mapeamento explícito assento -> Player/Deck) e cria a partida
    correspondente neste pod. Autenticado por token estático — pensado pra
    ser chamado manualmente via curl/httpie, não pelo navegador. Ver
    docs/superpowers/specs/2026-09-08-edhplay-match-capture-design.md.
    """

    def dispatch(self, request, *args, **kwargs):
        expected_token = settings.IMPORT_API_TOKEN
        auth_header = request.headers.get("Authorization", "")
        if not expected_token or auth_header != f"Bearer {expected_token}":
            return JsonResponse({"error": "unauthorized"}, status=401)
        self.pod = get_object_or_404(Pod, slug=kwargs["pod_slug"])
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"errors": ["Corpo da requisição não é um JSON válido."]}, status=400)

        match = payload.get("match")
        seat_mappings = payload.get("seat_mappings")
        if not isinstance(match, dict) or not isinstance(seat_mappings, list):
            return JsonResponse(
                {"errors": ["O corpo precisa ter 'match' (objeto) e 'seat_mappings' (lista)."]},
                status=400,
            )

        errors = self._validate(match, seat_mappings)
        if errors:
            return JsonResponse({"errors": errors}, status=400)

        return JsonResponse({"status": "validated"}, status=200)

    def _validate(self, match, seat_mappings):
        errors = []

        if match.get("schema_version") != 1:
            errors.append("match.schema_version precisa ser 1.")

        seats = match.get("seats")
        if not isinstance(seats, list) or not seats:
            errors.append("match.seats precisa ser uma lista não vazia.")
            return errors

        seat_numbers = set()
        winners = 0
        for seat in seats:
            if not isinstance(seat, dict) or "seat" not in seat:
                errors.append("Cada item de match.seats precisa ter 'seat'.")
                continue
            seat_numbers.add(seat["seat"])
            if seat.get("is_winner"):
                winners += 1
        if winners != 1:
            errors.append("Exatamente um assento em match.seats precisa ter is_winner=true.")

        mapping_by_seat = {}
        for mapping in seat_mappings:
            if not isinstance(mapping, dict) or "seat" not in mapping or "player_id" not in mapping:
                errors.append("Cada item de seat_mappings precisa ter 'seat' e 'player_id'.")
                continue
            mapping_by_seat[mapping["seat"]] = mapping

        missing = seat_numbers - mapping_by_seat.keys()
        if missing:
            errors.append(f"Faltando mapeamento em seat_mappings para o(s) assento(s): {sorted(missing)}.")

        used_player_ids = []
        for seat_number in seat_numbers:
            mapping = mapping_by_seat.get(seat_number)
            if mapping is None:
                continue
            player = Player.objects.filter(pk=mapping["player_id"], pod=self.pod).first()
            if player is None:
                errors.append(
                    f"Assento {seat_number}: player_id {mapping['player_id']} não pertence a este pod."
                )
                continue
            used_player_ids.append(player.id)

            deck_id = mapping.get("deck_id")
            if deck_id is not None and not Deck.objects.filter(pk=deck_id, player=player).exists():
                errors.append(
                    f"Assento {seat_number}: deck_id {deck_id} não pertence ao player_id {mapping['player_id']}."
                )

        duplicates = sorted({pid for pid in used_player_ids if used_player_ids.count(pid) > 1})
        if duplicates:
            errors.append(f"player_id repetido em mais de um assento: {duplicates}.")

        return errors
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.core.tests`
Expected: PASS (all `GameImportAuthTests` and `GameImportValidationTests`
cases — 12 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/core/views/game_import.py apps/core/tests.py
git commit -m "$(cat <<'EOF'
Validate seat mappings, pod ownership and winner count before import

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Create the Game and GameParticipants

**Files:**
- Modify: `apps/core/views/game_import.py`
- Modify: `apps/core/tests.py`

**Interfaces:**
- Consumes: `self.pod`, `self._validate()` (Tasks 1–2).
- Produces: `GameImportView._create_game(self, match: dict, seat_mappings:
  list) -> tuple[Game, list[str]]` (the created `Game` and a list of
  non-fatal warning strings). `post()` now returns `201` with `{"game_id",
  "url", "warnings"}` on success.

- [ ] **Step 1: Write the failing tests**

Add to `apps/core/tests.py`:

```python
@override_settings(IMPORT_API_TOKEN="test-token")
class GameImportCreationTests(TestCase):
    def setUp(self):
        self.pod = Pod.objects.create(name="Pod de Teste")
        self.player1 = Player.objects.create(pod=self.pod, name="Adinan")
        self.player2 = Player.objects.create(pod=self.pod, name="Bruno")
        self.player3 = Player.objects.create(pod=self.pod, name="Carol")
        self.deck1 = Deck.objects.create(player=self.player1)
        self.mvp_card = Card.objects.create(name="Toxic Deluge")
        self.url = reverse("core:game-import", kwargs={"pod_slug": self.pod.slug})

    def _post(self, body):
        return self.client.post(
            self.url,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION="Bearer test-token",
        )

    def test_creates_game_and_participants_with_correct_placement_and_kills(self):
        body = {
            "match": {
                "schema_version": 1,
                "source": "edhplay",
                "captured_at": "2026-09-08T21:00:00Z",
                "turn_count": 8,
                "win_condition": "Dano de Comandante",
                "notes": "Mesa boa",
                "seats": [
                    {
                        "seat": 1, "display_name": "AdinanP", "is_winner": True,
                        "eliminated_on_turn": None, "peak_life_total": 42,
                        "mvp_card": "toxic deluge", "board_wipes_count": 1,
                        "counterspell_count": 0, "complaint_count": 0,
                        "felt_salty": False, "fun_rating": 5,
                    },
                    {
                        "seat": 2, "display_name": "BrunoB", "is_winner": False,
                        "eliminated_on_turn": 6, "peak_life_total": 30,
                        "board_wipes_count": 0, "counterspell_count": 2,
                        "complaint_count": 1, "felt_salty": True, "fun_rating": 3,
                    },
                    {
                        "seat": 3, "display_name": "CarolC", "is_winner": False,
                        "eliminated_on_turn": 3, "peak_life_total": 20,
                        "board_wipes_count": 0, "counterspell_count": 0,
                        "complaint_count": 0, "felt_salty": False, "fun_rating": None,
                    },
                ],
                "eliminations": [
                    {"victim_seat": 3, "killer_seat": 2, "turn": 3},
                    {"victim_seat": 2, "killer_seat": 1, "turn": 6},
                ],
            },
            "seat_mappings": [
                {"seat": 1, "player_id": self.player1.id, "deck_id": self.deck1.id},
                {"seat": 2, "player_id": self.player2.id},
                {"seat": 3, "player_id": self.player3.id},
            ],
        }

        response = self._post(body)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        game = Game.objects.get(pk=data["game_id"])
        self.assertEqual(game.pod, self.pod)
        self.assertEqual(game.turn_count, 8)
        self.assertEqual(game.notes, "Mesa boa")
        self.assertEqual(game.win_condition, "commander_damage")

        participants = {p.player_id: p for p in game.participants.all()}
        winner = participants[self.player1.id]
        self.assertEqual(winner.placement, 1)
        self.assertEqual(winner.deck_id, self.deck1.id)
        self.assertEqual(winner.kill_count, 1)
        self.assertEqual(winner.mvp_card, self.mvp_card)

        second = participants[self.player2.id]
        self.assertEqual(second.placement, 2)
        self.assertIsNone(second.deck_id)
        self.assertEqual(second.kill_count, 1)
        self.assertTrue(second.felt_salty)

        third = participants[self.player3.id]
        self.assertEqual(third.placement, 3)
        self.assertEqual(third.kill_count, 0)

    def test_self_elimination_is_recorded(self):
        body = {
            "match": {
                "schema_version": 1,
                "source": "edhplay",
                "captured_at": "2026-09-08T21:00:00Z",
                "turn_count": 4,
                "win_condition": "Combate",
                "notes": "",
                "seats": [
                    {"seat": 1, "display_name": "AdinanP", "is_winner": True, "eliminated_on_turn": None},
                    {"seat": 2, "display_name": "BrunoB", "is_winner": False, "eliminated_on_turn": 2},
                ],
                "eliminations": [{"victim_seat": 2, "killer_seat": 2, "turn": 2}],
            },
            "seat_mappings": [
                {"seat": 1, "player_id": self.player1.id},
                {"seat": 2, "player_id": self.player2.id},
            ],
        }

        response = self._post(body)

        game = Game.objects.get(pk=response.json()["game_id"])
        loser = game.participants.get(player=self.player2)
        self.assertTrue(loser.is_self_elimination)
        self.assertEqual(loser.kill_count, 0)

    def test_unknown_mvp_card_name_is_a_warning_not_a_failure(self):
        body = {
            "match": {
                "schema_version": 1,
                "source": "edhplay",
                "captured_at": "2026-09-08T21:00:00Z",
                "turn_count": 3,
                "win_condition": "Mill",
                "notes": "",
                "seats": [
                    {
                        "seat": 1, "display_name": "AdinanP", "is_winner": True,
                        "eliminated_on_turn": None, "mvp_card": "Carta Que Não Existe",
                    },
                    {"seat": 2, "display_name": "BrunoB", "is_winner": False, "eliminated_on_turn": 2},
                ],
                "eliminations": [],
            },
            "seat_mappings": [
                {"seat": 1, "player_id": self.player1.id},
                {"seat": 2, "player_id": self.player2.id},
            ],
        }

        response = self._post(body)

        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertEqual(len(data["warnings"]), 1)
        self.assertIn("Carta Que Não Existe", data["warnings"][0])
        game = Game.objects.get(pk=data["game_id"])
        winner = game.participants.get(player=self.player1)
        self.assertIsNone(winner.mvp_card)
```

Add `Game` and `GameParticipant` to the `apps.core.models` import already
at the top of `apps/core/tests.py` (extend the existing `from
apps.core.models import Deck, Player` line from Task 2):
```python
from apps.core.models import Deck, Game, GameParticipant, Player
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.core.tests.GameImportCreationTests`
Expected: FAIL — `post()` still returns the Task 2 stub
(`{"status": "validated"}`, 200) instead of creating anything.

- [ ] **Step 3: Write the implementation**

Update `apps/core/views/game_import.py` — grow the import block, replace
`post()`'s last line, and add `_create_game()`:

```python
import json
from datetime import datetime

from django.conf import settings
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.views import View

from apps.cards.models import Card
from apps.core.models import Deck, Game, GameParticipant, Player, resolve_win_condition
from apps.pods.models import Pod


class GameImportView(View):
    """
    Recebe o JSON exportado pela extensão EDHPlay Match Logger (embrulhado
    com um mapeamento explícito assento -> Player/Deck) e cria a partida
    correspondente neste pod. Autenticado por token estático — pensado pra
    ser chamado manualmente via curl/httpie, não pelo navegador. Ver
    docs/superpowers/specs/2026-09-08-edhplay-match-capture-design.md.
    """

    def dispatch(self, request, *args, **kwargs):
        expected_token = settings.IMPORT_API_TOKEN
        auth_header = request.headers.get("Authorization", "")
        if not expected_token or auth_header != f"Bearer {expected_token}":
            return JsonResponse({"error": "unauthorized"}, status=401)
        self.pod = get_object_or_404(Pod, slug=kwargs["pod_slug"])
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        try:
            payload = json.loads(request.body or b"{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({"errors": ["Corpo da requisição não é um JSON válido."]}, status=400)

        match = payload.get("match")
        seat_mappings = payload.get("seat_mappings")
        if not isinstance(match, dict) or not isinstance(seat_mappings, list):
            return JsonResponse(
                {"errors": ["O corpo precisa ter 'match' (objeto) e 'seat_mappings' (lista)."]},
                status=400,
            )

        errors = self._validate(match, seat_mappings)
        if errors:
            return JsonResponse({"errors": errors}, status=400)

        game, warnings = self._create_game(match, seat_mappings)
        return JsonResponse(
            {
                "game_id": game.pk,
                "url": reverse("core:game-detail", kwargs={"pod_slug": self.pod.slug, "pk": game.pk}),
                "warnings": warnings,
            },
            status=201,
        )

    def _validate(self, match, seat_mappings):
        errors = []

        if match.get("schema_version") != 1:
            errors.append("match.schema_version precisa ser 1.")

        seats = match.get("seats")
        if not isinstance(seats, list) or not seats:
            errors.append("match.seats precisa ser uma lista não vazia.")
            return errors

        seat_numbers = set()
        winners = 0
        for seat in seats:
            if not isinstance(seat, dict) or "seat" not in seat:
                errors.append("Cada item de match.seats precisa ter 'seat'.")
                continue
            seat_numbers.add(seat["seat"])
            if seat.get("is_winner"):
                winners += 1
        if winners != 1:
            errors.append("Exatamente um assento em match.seats precisa ter is_winner=true.")

        mapping_by_seat = {}
        for mapping in seat_mappings:
            if not isinstance(mapping, dict) or "seat" not in mapping or "player_id" not in mapping:
                errors.append("Cada item de seat_mappings precisa ter 'seat' e 'player_id'.")
                continue
            mapping_by_seat[mapping["seat"]] = mapping

        missing = seat_numbers - mapping_by_seat.keys()
        if missing:
            errors.append(f"Faltando mapeamento em seat_mappings para o(s) assento(s): {sorted(missing)}.")

        used_player_ids = []
        for seat_number in seat_numbers:
            mapping = mapping_by_seat.get(seat_number)
            if mapping is None:
                continue
            player = Player.objects.filter(pk=mapping["player_id"], pod=self.pod).first()
            if player is None:
                errors.append(
                    f"Assento {seat_number}: player_id {mapping['player_id']} não pertence a este pod."
                )
                continue
            used_player_ids.append(player.id)

            deck_id = mapping.get("deck_id")
            if deck_id is not None and not Deck.objects.filter(pk=deck_id, player=player).exists():
                errors.append(
                    f"Assento {seat_number}: deck_id {deck_id} não pertence ao player_id {mapping['player_id']}."
                )

        duplicates = sorted({pid for pid in used_player_ids if used_player_ids.count(pid) > 1})
        if duplicates:
            errors.append(f"player_id repetido em mais de um assento: {duplicates}.")

        return errors

    def _create_game(self, match, seat_mappings):
        mapping_by_seat = {m["seat"]: m for m in seat_mappings}
        eliminations = match.get("eliminations") or []

        kill_counts = {}
        self_eliminated_seats = set()
        for elim in eliminations:
            killer = elim.get("killer_seat")
            victim = elim.get("victim_seat")
            if killer is not None:
                kill_counts[killer] = kill_counts.get(killer, 0) + 1
                if killer == victim:
                    self_eliminated_seats.add(victim)

        seats = match["seats"]
        winner_seat = next(s for s in seats if s.get("is_winner"))
        placement_by_seat = {winner_seat["seat"]: 1}
        eliminated_seats = sorted(
            (s for s in seats if s["seat"] != winner_seat["seat"]),
            key=lambda s: (s.get("eliminated_on_turn") is None, -(s.get("eliminated_on_turn") or 0)),
        )
        for index, seat in enumerate(eliminated_seats, start=2):
            placement_by_seat[seat["seat"]] = index

        game_date = None
        captured_at = match.get("captured_at")
        if captured_at:
            game_date = datetime.fromisoformat(captured_at.replace("Z", "+00:00")).date()

        warnings = []

        with transaction.atomic():
            game = Game.objects.create(
                pod=self.pod,
                date=game_date,
                win_condition=resolve_win_condition(match.get("win_condition") or ""),
                turn_count=match.get("turn_count"),
                notes=match.get("notes") or "",
            )

            for seat in seats:
                seat_number = seat["seat"]
                mapping = mapping_by_seat[seat_number]
                player = Player.objects.get(pk=mapping["player_id"], pod=self.pod)
                deck = None
                deck_id = mapping.get("deck_id")
                if deck_id is not None:
                    deck = Deck.objects.get(pk=deck_id, player=player)

                mvp_card = None
                mvp_card_name = seat.get("mvp_card")
                if mvp_card_name:
                    mvp_card = Card.objects.filter(name__iexact=mvp_card_name).first()
                    if mvp_card is None:
                        warnings.append(f"Assento {seat_number}: carta MVP '{mvp_card_name}' não encontrada.")

                GameParticipant.objects.create(
                    game=game,
                    player=player,
                    deck=deck,
                    placement=placement_by_seat.get(seat_number),
                    kill_count=kill_counts.get(seat_number, 0),
                    mvp_card=mvp_card,
                    peak_life_total=seat.get("peak_life_total"),
                    board_wipes_count=seat.get("board_wipes_count") or 0,
                    counterspell_count=seat.get("counterspell_count") or 0,
                    complaint_count=seat.get("complaint_count") or 0,
                    is_self_elimination=seat_number in self_eliminated_seats,
                    starting_seat=seat_number,
                    felt_salty=bool(seat.get("felt_salty")),
                    fun_rating=seat.get("fun_rating"),
                )

        return game, warnings
```

- [ ] **Step 4: Run the full test file**

Run: `python manage.py test apps.core.tests`
Expected: PASS (all 15 tests across `GameImportAuthTests`,
`GameImportValidationTests`, and `GameImportCreationTests`).

- [ ] **Step 5: Manual smoke test against a real pod**

With the dev server running (`python manage.py runserver`) and
`IMPORT_API_TOKEN` set in `.env`, pick a real pod slug and two real
`Player`/`Deck` ids from your database (via `/pod-admin/` or `manage.py
shell`), then:

```bash
curl -X POST http://localhost:8000/p/<pod-slug>/partidas/importar/ \
  -H "Authorization: Bearer <seu-IMPORT_API_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "match": {
      "schema_version": 1,
      "source": "edhplay",
      "captured_at": "2026-09-08T21:00:00Z",
      "turn_count": 6,
      "win_condition": "Dano de Comandante",
      "notes": "Importado manualmente pra teste",
      "seats": [
        {"seat": 1, "display_name": "Teste1", "is_winner": true, "eliminated_on_turn": null},
        {"seat": 2, "display_name": "Teste2", "is_winner": false, "eliminated_on_turn": 4}
      ],
      "eliminations": [{"victim_seat": 2, "killer_seat": 1, "turn": 4}]
    },
    "seat_mappings": [
      {"seat": 1, "player_id": <player-id-1>},
      {"seat": 2, "player_id": <player-id-2>}
    ]
  }'
```

Expected: `201` with a `game_id` and `url`; opening that `url` in the
browser shows the new partida on the pod's game list with the right
placement, wincon and notes.

- [ ] **Step 6: Commit**

```bash
git add apps/core/views/game_import.py apps/core/tests.py
git commit -m "$(cat <<'EOF'
Create Game and GameParticipants from the EDHPlay import payload

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
