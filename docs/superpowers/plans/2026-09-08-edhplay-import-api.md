# EDHPlay Import API Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a pod-scoped API endpoint to Comandometro that accepts the
JSON produced by the EDHPlay Match Logger browser extension (wrapped with
an explicit seat→Player/Deck mapping) and creates the corresponding `Game`
and `GameParticipant` records — plus two read-only GET endpoints the
extension calls directly from the browser to populate its sidebar selects
(pod players, known win conditions) before it exports that JSON.

**Architecture:** Three new Django class-based views under
`apps/core/views/`, following the existing `*.py` + `JsonResponse`
conventions already used elsewhere in this app (no DRF in this project).
The write endpoint (`GameImportView`, Tasks 1-3) is authenticated by a
static bearer token from an environment variable — not a Django session —
since it's called manually via curl/httpie, never from a browser. The two
read endpoints (Tasks 5-6) are a fundamentally different trust boundary:
they're called directly by the extension's content/background script
running in the user's Chrome, cross-origin, with no Django session and no
CSRF token available — so they get their own per-pod bearer token (Task 4),
a hand-rolled CORS allowlist for exactly one origin, and a basic cache-based
throttle. They deliberately do **not** reuse `IMPORT_API_TOKEN` — a token
handed to browser-side extension code and a token you type into curl by
hand are different trust levels, and a leaked one should never expose the
other. All three views are covered by `django.test.TestCase` (the only test
style already used in this repo).

**Tech Stack:** Django (existing stack — no new dependencies; no
`django-cors-headers`, no cache backend beyond Django's default
`LocMemCache`).

## Global Constraints

- The endpoint is authenticated by a static token from the
  `IMPORT_API_TOKEN` environment variable, checked via an `Authorization:
  Bearer <token>` header — no session involved. It is `csrf_exempt`
  (`@method_decorator(csrf_exempt, name="dispatch")`) because the project's
  `CsrfViewMiddleware` is active globally and would otherwise reject any
  POST with no CSRF cookie, which a curl/httpie call never has — this is
  necessary for the endpoint to work at all outside of Django's test
  client (whose default `Client()` skips CSRF enforcement, which is why
  this would otherwise look fine in tests and then fail for real).
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
- No web UI, no DRF, no new database models for the import endpoint — the
  existing `Game` / `GameParticipant` fields already cover what it writes
  (see the design spec:
  `docs/superpowers/specs/2026-09-08-edhplay-match-capture-design.md`).
- The two read endpoints (`GET /p/<pod_slug>/api/players/`, `GET
  /p/<pod_slug>/api/win-conditions/`) are authenticated by a **per-pod**
  token (`Pod.read_api_token`, a new field mirroring the existing
  `Pod.invite_token` pattern) via `Authorization: Bearer <token>` — not
  `IMPORT_API_TOKEN`, not a session. A leak only exposes that one pod's
  player names and custom win-condition labels, and it's regenerable from
  the pod settings page without touching an env var or redeploying.
- Because the read token is per-pod, the pod must be resolved from the URL
  **before** the token can be checked — the opposite order from
  `GameImportView`'s global-token check. This is intentional, not an
  inconsistency: a global token can be checked with zero context, a
  per-pod one can't.
- CORS on the two read endpoints is hand-rolled on just those views (a
  small mixin), not `django-cors-headers` — restricted to exactly one
  allowlisted origin from `settings.EDHPLAY_EXTENSION_ORIGIN` (e.g.
  `chrome-extension://<the-extension's-id>`), echoed back verbatim, never
  `*`. No other view in the project gets CORS headers.
- **Dependency on the extension repo:** this only works if
  `edhplay-match-logger`'s `chrome-extension://<id>` origin is stable
  across installs/reloads. An unpacked extension's ID is derived from its
  install path unless the manifest pins one — add a `"key"` field to
  `edhplay-match-logger/manifest.json` (a generated public key) before
  relying on this CORS allowlist; otherwise `EDHPLAY_EXTENSION_ORIGIN`
  drifts every time the extension is reloaded unpacked. Out of scope for
  *this* plan (it's a change to the other repo) but called out here because
  the CORS piece is silently broken without it.
- Rate limiting on the two read endpoints uses Django's default cache
  (`LocMemCache` — no Redis, no new setting) keyed by the pod's read token:
  a fixed request budget per 60s window, `429` past it. This is
  per-process, not exact under multiple gunicorn workers, and only kicks in
  *after* a valid token is presented (the token itself, 122 bits of
  entropy, is the actual defense against guessing) — proportionate for a
  personal-use tool, not a hardened public API.
- CORS is defense-in-depth here, not the access control: since the read
  token is an explicit header the extension sends (not an ambient cookie),
  no other website's JS can forge a request with it just by riding the
  user's browser. The token is what actually gates access; CORS only
  limits which origins can *see* a successful response.
- Scope is deliberately just players + win conditions. Decks, game
  history, or any other pod data are **not** part of this plan — `Task 5`'s
  `PodReadApiView` base (CORS + per-pod token + throttle) exists precisely
  so a future read-only endpoint (e.g. `GET /api/decks/`) is a thin
  `PodReadApiView` subclass with one `get()` method, not a new auth/CORS
  story each time.

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
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.pods.models import Pod


@method_decorator(csrf_exempt, name="dispatch")
class GameImportView(View):
    """
    Recebe o JSON exportado pela extensão EDHPlay Match Logger (embrulhado
    com um mapeamento explícito assento -> Player/Deck) e cria a partida
    correspondente neste pod. Autenticado por token estático — pensado pra
    ser chamado manualmente via curl/httpie, não pelo navegador. csrf_exempt
    porque não há cookie de sessão nem token CSRF nessa chamada (o
    CsrfViewMiddleware do projeto rejeitaria qualquer POST sem isso, mesmo
    autenticado pelo Bearer token). Ver
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
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.core.models import Deck, Player
from apps.pods.models import Pod


@method_decorator(csrf_exempt, name="dispatch")
class GameImportView(View):
    """
    Recebe o JSON exportado pela extensão EDHPlay Match Logger (embrulhado
    com um mapeamento explícito assento -> Player/Deck) e cria a partida
    correspondente neste pod. Autenticado por token estático — pensado pra
    ser chamado manualmente via curl/httpie, não pelo navegador. csrf_exempt
    porque não há cookie de sessão nem token CSRF nessa chamada (o
    CsrfViewMiddleware do projeto rejeitaria qualquer POST sem isso, mesmo
    autenticado pelo Bearer token). Ver
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
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt

from apps.cards.models import Card
from apps.core.models import Deck, Game, GameParticipant, Player, resolve_win_condition
from apps.pods.models import Pod


@method_decorator(csrf_exempt, name="dispatch")
class GameImportView(View):
    """
    Recebe o JSON exportado pela extensão EDHPlay Match Logger (embrulhado
    com um mapeamento explícito assento -> Player/Deck) e cria a partida
    correspondente neste pod. Autenticado por token estático — pensado pra
    ser chamado manualmente via curl/httpie, não pelo navegador. csrf_exempt
    porque não há cookie de sessão nem token CSRF nessa chamada (o
    CsrfViewMiddleware do projeto rejeitaria qualquer POST sem isso, mesmo
    autenticado pelo Bearer token). Ver
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

---

### Task 4: Per-pod read token (`Pod.read_api_token`)

**Files:**
- Modify: `apps/pods/models/pod.py`
- Create: `apps/pods/migrations/0002_pod_read_api_token.py`
- Modify: `apps/pods/views/pod_settings.py`
- Modify: `apps/pods/templates/pods/pod_settings.html`
- Create: `apps/pods/tests.py`

**Interfaces:**
- Produces: `Pod.read_api_token` (`UUIDField`, `default=uuid4`, `unique=True`),
  `Pod.regenerate_read_api_token(self) -> None`. Task 5 depends on
  `pod.read_api_token` existing and being comparable as a string via
  `f"Bearer {pod.read_api_token}"`.

- [ ] **Step 1: Write the failing tests**

Create `apps/pods/tests.py` (this app has no test file yet):
```python
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.pods.models import Membership, Pod

User = get_user_model()


class PodReadApiTokenTests(TestCase):
    def test_pod_gets_a_read_api_token_by_default(self):
        pod = Pod.objects.create(name="Pod de Teste")
        self.assertIsNotNone(pod.read_api_token)

    def test_two_pods_never_share_a_read_api_token(self):
        pod1 = Pod.objects.create(name="Pod 1")
        pod2 = Pod.objects.create(name="Pod 2")
        self.assertNotEqual(pod1.read_api_token, pod2.read_api_token)

    def test_regenerate_read_api_token_changes_the_value(self):
        pod = Pod.objects.create(name="Pod de Teste")
        original = pod.read_api_token
        pod.regenerate_read_api_token()
        self.assertNotEqual(pod.read_api_token, original)


class PodSettingsReadTokenViewTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create_user(username="owner", password="pass1234")
        self.pod = Pod.objects.create(name="Pod de Teste")
        Membership.objects.create(pod=self.pod, user=self.owner, role=Membership.Role.OWNER)
        self.client.force_login(self.owner)
        self.url = reverse("pod:pod-settings", kwargs={"pod_slug": self.pod.slug})

    def test_settings_page_shows_the_read_api_token(self):
        response = self.client.get(self.url)
        self.assertContains(response, str(self.pod.read_api_token))

    def test_regenerate_read_token_action_changes_it_and_redirects(self):
        original = self.pod.read_api_token
        response = self.client.post(self.url, {"action": "regenerate_read_token"})
        self.pod.refresh_from_db()
        self.assertRedirects(response, self.url)
        self.assertNotEqual(self.pod.read_api_token, original)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.pods.tests`
Expected: FAIL — `Pod` has no `read_api_token` field yet.

- [ ] **Step 3: Add the field, migration, view action, and template block**

In `apps/pods/models/pod.py`, add the field (next to `invite_token`) and
the method (next to `regenerate_invite_token`):
```python
    read_api_token = models.UUIDField(
        default=uuid4,
        unique=True,
        help_text=(
            "Usado pela extensão EDHPlay Match Logger pra ler players/wincons "
            "deste pod; regenerar invalida o anterior"
        ),
    )
```
```python
    def regenerate_read_api_token(self):
        self.read_api_token = uuid4()
        self.save(update_fields=["read_api_token"])
```

Create `apps/pods/migrations/0002_pod_read_api_token.py`:
```python
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pods", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="pod",
            name="read_api_token",
            field=models.UUIDField(
                default=uuid.uuid4,
                unique=True,
                help_text=(
                    "Usado pela extensão EDHPlay Match Logger pra ler players/wincons "
                    "deste pod; regenerar invalida o anterior"
                ),
            ),
        ),
    ]
```

In `apps/pods/views/pod_settings.py`, add a new branch in `post()` right
after the `regenerate_invite` one:
```python
        if action == "regenerate_read_token":
            self.pod.regenerate_read_api_token()
            messages.success(request, "Token de leitura da extensão regenerado.")
            return redirect("pod:pod-settings", pod_slug=self.pod.slug)
```

In `apps/pods/templates/pods/pod_settings.html`, add a new block right
after the existing "Link de Convite" block (before "Membros"), mirroring
its markup:
```html
  <div class="bg-white border border-gray-200 rounded-xl shadow-sm p-6 space-y-4">
    <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">Token de Leitura (Extensão EDHPlay)</h2>
    <p class="text-xs text-gray-500">Cole esse token nas opções da extensão EDHPlay Match Logger pra ela ler os jogadores e wincons deste pod.</p>
    <div class="flex items-center gap-3">
      <input type="text" readonly value="{{ pod.read_api_token }}" class="form-input font-mono text-xs" />
    </div>
    <form method="post">
      {% csrf_token %}
      <input type="hidden" name="action" value="regenerate_read_token" />
      <button type="submit" class="text-sm font-semibold px-4 py-2 rounded-lg border border-gray-300 text-gray-700 hover:bg-gray-50 transition">
        Gerar novo token (invalida o anterior)
      </button>
    </form>
  </div>
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.pods.tests`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/pods/models/pod.py apps/pods/migrations/0002_pod_read_api_token.py apps/pods/views/pod_settings.py apps/pods/templates/pods/pod_settings.html apps/pods/tests.py
git commit -m "$(cat <<'EOF'
Add a per-pod read API token, regenerable from pod settings

Mirrors the existing invite_token pattern. This is the credential the
EDHPlay Match Logger extension will use for the read-only endpoints
added in the next tasks — deliberately separate from IMPORT_API_TOKEN.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 5: `GET /p/<pod_slug>/api/players/` (plus the shared CORS/auth/throttle mixins)

**Files:**
- Create: `apps/core/views/pod_read_api.py`
- Modify: `apps/core/views/__init__.py`
- Modify: `apps/core/urls.py`
- Modify: `config/settings/base.py`
- Modify: `.env.example`
- Modify: `apps/core/tests.py`

**Interfaces:**
- Consumes: `Pod` (`apps.pods.models`), `settings.EDHPLAY_EXTENSION_ORIGIN`,
  Django's default cache (`django.core.cache.cache`).
- Produces: `CorsAllowedExtensionMixin`, `PodReadTokenRequiredMixin`,
  `ReadApiRateLimitMixin` (each a `dispatch()`-based mixin, composable in
  that order), `PodReadApiView` (the three mixins + `View`, no `get()` of
  its own — the shared base every read endpoint extends), `PodPlayersView`.
  URL name `core:api-players` → `/p/<pod_slug>/api/players/`. Task 6
  imports `PodReadApiView` from this same module.

- [ ] **Step 1: Write the failing tests**

Add one new import line near the top of `apps/core/tests.py` (`Player` is
already imported there as of Task 3's `from apps.core.models import Deck,
Game, GameParticipant, Player, resolve_win_condition` — nothing to change
on that line):
```python
from django.core.cache import cache
```

New test class, appended to the file:

```python
@override_settings(EDHPLAY_EXTENSION_ORIGIN="chrome-extension://fakeidfortests")
class PodPlayersViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.pod = Pod.objects.create(name="Pod de Teste")
        self.player1 = Player.objects.create(pod=self.pod, name="Adinan Paiva", nickname="AdinanP")
        self.player2 = Player.objects.create(pod=self.pod, name="Bruno Silva")
        self.url = reverse("core:api-players", kwargs={"pod_slug": self.pod.slug})
        self.auth_header = f"Bearer {self.pod.read_api_token}"

    def test_rejects_request_without_token(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_rejects_request_with_wrong_token(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION="Bearer wrong-token")
        self.assertEqual(response.status_code, 401)

    def test_returns_404_for_unknown_pod_slug(self):
        url = reverse("core:api-players", kwargs={"pod_slug": "nao-existe"})
        response = self.client.get(url, HTTP_AUTHORIZATION=self.auth_header)
        self.assertEqual(response.status_code, 404)

    def test_returns_players_ordered_by_name(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION=self.auth_header)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["players"],
            [
                {"id": self.player1.id, "name": "Adinan Paiva", "nickname": "AdinanP"},
                {"id": self.player2.id, "name": "Bruno Silva", "nickname": ""},
            ],
        )

    def test_adds_cors_headers_only_for_the_allowed_extension_origin(self):
        allowed = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=self.auth_header,
            HTTP_ORIGIN="chrome-extension://fakeidfortests",
        )
        self.assertEqual(allowed["Access-Control-Allow-Origin"], "chrome-extension://fakeidfortests")

        other = self.client.get(
            self.url,
            HTTP_AUTHORIZATION=self.auth_header,
            HTTP_ORIGIN="https://evil.example.com",
        )
        self.assertNotIn("Access-Control-Allow-Origin", other)

    def test_options_preflight_answers_with_cors_headers(self):
        response = self.client.options(self.url, HTTP_ORIGIN="chrome-extension://fakeidfortests")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["Access-Control-Allow-Origin"], "chrome-extension://fakeidfortests")
        self.assertEqual(response["Access-Control-Allow-Headers"], "Authorization")

    def test_throttles_after_exceeding_the_rate_limit(self):
        from apps.core.views.pod_read_api import PodPlayersView

        PodPlayersView.rate_limit = 2
        try:
            for _ in range(2):
                response = self.client.get(self.url, HTTP_AUTHORIZATION=self.auth_header)
                self.assertEqual(response.status_code, 200)
            response = self.client.get(self.url, HTTP_AUTHORIZATION=self.auth_header)
            self.assertEqual(response.status_code, 429)
        finally:
            del PodPlayersView.rate_limit
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.core.tests.PodPlayersViewTests`
Expected: FAIL — `core:api-players` doesn't resolve yet, `Pod` has no
`read_api_token` attribute error would already be fixed by Task 4, so this
should fail specifically on the missing URL/view.

- [ ] **Step 3: Write the implementation**

Add to `config/settings/base.py`, right after `IMPORT_API_TOKEN`:
```python
# Origem exata (chrome-extension://<id>) liberada pra ler os endpoints
# GET /p/<pod_slug>/api/players/ e /api/win-conditions/. Vazio = CORS
# nunca liberado (fail-closed) até isso ser configurado de propósito.
EDHPLAY_EXTENSION_ORIGIN = env("EDHPLAY_EXTENSION_ORIGIN", default="")
```

Add to `.env.example`, after `IMPORT_API_TOKEN=`:
```
EDHPLAY_EXTENSION_ORIGIN=
```

Create `apps/core/views/pod_read_api.py`:
```python
from django.conf import settings
from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.pods.models import Pod


class CorsAllowedExtensionMixin:
    """
    Libera CORS só pra origem fixa da extensão EDHPlay Match Logger
    (settings.EDHPLAY_EXTENSION_ORIGIN, ex: "chrome-extension://<id>").
    Qualquer outra origem (ou nenhuma, como uma chamada via curl) segue sem
    os headers de CORS — quem bloqueia a leitura da resposta nesse caso é o
    navegador de quem chamou, não este código. O token de leitura por pod
    é o controle de acesso de verdade; isto é reforço a mais.
    """

    def dispatch(self, request, *args, **kwargs):
        origin = request.headers.get("Origin", "")
        allowed_origin = settings.EDHPLAY_EXTENSION_ORIGIN
        is_allowed = bool(allowed_origin) and origin == allowed_origin

        if request.method == "OPTIONS":
            response = HttpResponse(status=204)
            if is_allowed:
                response["Access-Control-Allow-Headers"] = "Authorization"
                response["Access-Control-Allow-Methods"] = "GET, OPTIONS"
                response["Access-Control-Max-Age"] = "86400"
        else:
            response = super().dispatch(request, *args, **kwargs)

        if is_allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Vary"] = "Origin"
        return response


class PodReadTokenRequiredMixin:
    """
    Resolve o Pod pela slug da URL e exige Authorization: Bearer
    <pod.read_api_token>. Ordem invertida em relação ao GameImportView (que
    checa o token global antes de saber o pod): aqui o token é por pod, não
    dá pra validar sem saber qual pod primeiro.
    """

    def dispatch(self, request, *args, **kwargs):
        self.pod = get_object_or_404(Pod, slug=kwargs["pod_slug"])
        provided = request.headers.get("Authorization", "")
        expected = f"Bearer {self.pod.read_api_token}"
        if provided != expected:
            return JsonResponse({"error": "unauthorized"}, status=401)
        return super().dispatch(request, *args, **kwargs)


class ReadApiRateLimitMixin:
    """
    Throttle simples por token de leitura, no cache padrão do Django
    (LocMemCache se nada mais estiver configurado — por processo, não é
    exato entre workers, mas corta abuso grosseiro sem exigir Redis).
    """

    rate_limit = 30
    rate_limit_window_seconds = 60

    def dispatch(self, request, *args, **kwargs):
        key = f"edhplay-read-throttle:{self.pod.read_api_token}"
        if not self._allow_request(key, self.rate_limit, self.rate_limit_window_seconds):
            return JsonResponse({"error": "too_many_requests"}, status=429)
        return super().dispatch(request, *args, **kwargs)

    @staticmethod
    def _allow_request(key, limit, window_seconds):
        if cache.add(key, 1, timeout=window_seconds):
            return True
        try:
            count = cache.incr(key)
        except ValueError:
            cache.set(key, 1, timeout=window_seconds)
            return True
        return count <= limit


class PodReadApiView(CorsAllowedExtensionMixin, PodReadTokenRequiredMixin, ReadApiRateLimitMixin, View):
    """Base pros endpoints GET somente-leitura consumidos pela extensão."""


class PodPlayersView(PodReadApiView):
    def get(self, request, *args, **kwargs):
        players = self.pod.players.order_by("name").values("id", "name", "nickname")
        return JsonResponse({"players": list(players)})
```

Update `apps/core/views/__init__.py` to the following full content (adds
the import and the `__all__` entry for `PodPlayersView`):
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
from .pod_read_api import PodPlayersView
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
    "PodPlayersView",
    "DeckDetailView",
    "DeckCreateView",
    "DeckCreateAjaxView",
    "DeckListView",
    "DeckDecklistView",
]
```

Update `apps/core/urls.py` to the following full content (adds
`PodPlayersView` to the import block and a new path; unlike
`partidas/importar/` there's no `<int:pk>` pattern under `api/` to shadow,
so the new path's position in `urlpatterns` doesn't matter):
```python
from django.urls import path
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
    PodPlayersView,
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
    path("api/players/", PodPlayersView.as_view(), name="api-players"),
    path("decks/", DeckListView.as_view(), name="deck-list"),
    path("decks/novo/", DeckCreateView.as_view(), name="deck-create"),
    path("decks/novo/ajax/", DeckCreateAjaxView.as_view(), name="deck-create-ajax"),
    path("decks/<int:pk>/", DeckDetailView.as_view(), name="deck-detail"),
    path("decks/<int:pk>/lista/", DeckDecklistView.as_view(), name="deck-decklist"),
    path("decks/<int:pk>/excluir/", DeckDeleteView.as_view(), name="deck-delete"),
]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.core.tests.PodPlayersViewTests`
Expected: PASS (7 tests).

- [ ] **Step 5: Commit**

```bash
git add apps/core/views/pod_read_api.py apps/core/views/__init__.py apps/core/urls.py config/settings/base.py .env.example apps/core/tests.py
git commit -m "$(cat <<'EOF'
Add GET /p/<pod_slug>/api/players/ with per-pod token, CORS, and throttle

New PodReadApiView base (CORS allowlist + per-pod bearer token + basic
rate limit) shared by every read-only endpoint the browser extension
calls directly — deliberately separate from the write-side
IMPORT_API_TOKEN used by GameImportView.

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

### Task 6: `GET /p/<pod_slug>/api/win-conditions/`

**Files:**
- Modify: `apps/core/views/pod_read_api.py`
- Modify: `apps/core/views/__init__.py`
- Modify: `apps/core/urls.py`
- Modify: `apps/core/tests.py`

**Interfaces:**
- Consumes: `PodReadApiView` (Task 5), `wincon_suggestions(pod)` (already
  exists in `apps/core/models/game.py`, exported from `apps.core.models`).
- Produces: `PodWinConditionsView`. URL name `core:api-win-conditions` →
  `/p/<pod_slug>/api/win-conditions/`. Response shape:
  `{"win_conditions": [<label str>, ...]}` — a plain list of labels (not
  `{value, label}` pairs), matching exactly what `wincon_suggestions()`
  already returns and what the extension's sidebar `<datalist>` already
  expects (see `src/sidebar.ts`'s `WINCON_SUGGESTIONS` constant in the
  `edhplay-match-logger` plan — that hardcoded list is meant to be replaced
  by a fetch to this endpoint in a future update to that plan, not
  something to build here).

- [ ] **Step 1: Write the failing tests**

Append to `apps/core/tests.py` — no new imports needed, the test only
asserts on the JSON response, and `Game`, `GameParticipant`, `Player`,
`resolve_win_condition` are already imported as of Task 3:

```python
@override_settings(EDHPLAY_EXTENSION_ORIGIN="chrome-extension://fakeidfortests")
class PodWinConditionsViewTests(TestCase):
    def setUp(self):
        cache.clear()
        self.pod = Pod.objects.create(name="Pod de Teste")
        self.url = reverse("core:api-win-conditions", kwargs={"pod_slug": self.pod.slug})
        self.auth_header = f"Bearer {self.pod.read_api_token}"

    def test_rejects_request_without_token(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 401)

    def test_returns_known_wincon_labels(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION=self.auth_header)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Dano de Comandante", data["win_conditions"])
        self.assertIn("Combate", data["win_conditions"])

    def test_includes_custom_wincons_already_used_by_this_pod(self):
        player = Player.objects.create(pod=self.pod, name="Adinan")
        game = Game.objects.create(pod=self.pod, win_condition=resolve_win_condition("Roubo de Turnos"))
        GameParticipant.objects.create(game=game, player=player, placement=1)

        response = self.client.get(self.url, HTTP_AUTHORIZATION=self.auth_header)

        self.assertIn("Roubo de Turnos", response.json()["win_conditions"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test apps.core.tests.PodWinConditionsViewTests`
Expected: FAIL — `core:api-win-conditions` doesn't resolve yet.

- [ ] **Step 3: Write the implementation**

Add to `apps/core/views/pod_read_api.py` — one new import line and one new
class at the end:
```python
from apps.core.models import wincon_suggestions
```
```python
class PodWinConditionsView(PodReadApiView):
    def get(self, request, *args, **kwargs):
        return JsonResponse({"win_conditions": wincon_suggestions(self.pod)})
```

Update `apps/core/views/__init__.py` — change the `pod_read_api` import
line and add the `__all__` entry:
```python
from .pod_read_api import PodPlayersView, PodWinConditionsView
```
```python
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
    "PodPlayersView",
    "PodWinConditionsView",
    "DeckDetailView",
    "DeckCreateView",
    "DeckCreateAjaxView",
    "DeckListView",
    "DeckDecklistView",
]
```

Update `apps/core/urls.py` to the following full content (adds
`PodWinConditionsView` to the import block and a new path next to
`api/players/`):
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
    PodPlayersView,
    PodWinConditionsView,
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
    path("api/players/", PodPlayersView.as_view(), name="api-players"),
    path("api/win-conditions/", PodWinConditionsView.as_view(), name="api-win-conditions"),
    path("decks/", DeckListView.as_view(), name="deck-list"),
    path("decks/novo/", DeckCreateView.as_view(), name="deck-create"),
    path("decks/novo/ajax/", DeckCreateAjaxView.as_view(), name="deck-create-ajax"),
    path("decks/<int:pk>/", DeckDetailView.as_view(), name="deck-detail"),
    path("decks/<int:pk>/lista/", DeckDecklistView.as_view(), name="deck-decklist"),
    path("decks/<int:pk>/excluir/", DeckDeleteView.as_view(), name="deck-delete"),
]
```
(the `from django.urls import path` line at the top of the file is
unchanged from Task 1).

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test apps.core.tests`
Expected: PASS — the full file (`GameImportAuthTests`,
`GameImportValidationTests`, `GameImportCreationTests`,
`PodPlayersViewTests`, `PodWinConditionsViewTests`) all green.

- [ ] **Step 5: Commit**

```bash
git add apps/core/views/pod_read_api.py apps/core/views/__init__.py apps/core/urls.py apps/core/tests.py
git commit -m "$(cat <<'EOF'
Add GET /p/<pod_slug>/api/win-conditions/ for the extension's sidebar

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```
