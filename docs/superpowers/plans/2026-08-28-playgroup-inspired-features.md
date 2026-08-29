# Playgroup.gg-Inspired Features Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar os 9 itens aprovados no spec (`docs/superpowers/specs/2026-08-28-playgroup-inspired-features-design.md`): tela de Detalhe do Deck (hero banner, wincon breakdown, matchups/arqui-inimigo, partidas recentes), campos `starting_seat`/`felt_salty`/`fun_rating`, filtro de janela de tempo no dashboard, seção de posição na mesa, recordes de salt/diversão, e sparkline de tendência no perfil do jogador.

**Architecture:** Extensão direta do que já existe — mesmos padrões de `BaseUseCase`, views finas, templates Tailwind. Sem biblioteca de gráfico nova: o sparkline é SVG puro montado no Python. Sem mudança de infraestrutura (sem WebSocket, sem app novo).

**Tech Stack:** Django 6.1, Tailwind CDN (mesmo tema claro já usado), SVG inline.

## Global Constraints

- Sem suite de testes automatizados — verificação via `manage.py check`, scripts `.venv/bin/python -c "..."`, e `django.test.Client` + `setup_test_environment()`.
- Sempre `.venv/bin/python`, nunca `python`/`python3` do shell.
- Um use case por módulo em `apps/core/use_cases/`, reexportado em `__init__.py`; uma view por módulo em `apps/core/views/`, idem.
- Todo use case herda de `apps.shared.use_cases.BaseUseCase`.
- Campos novos sempre opcionais (`null=True, blank=True` ou `default=`), nunca obrigatórios — ninguém é forçado a preencher tudo toda partida.
- "Recordes do Pod" (board wipes, counterspells, etc.) é seção **sempre all-time** — não é afetada pelo filtro de janela de tempo do dashboard (não faz sentido dizer "recorde dos últimos 7 dias" pra algo com framing de hall da fama).
- Commits pequenos, um por tarefa.

---

### Task 1: Campos novos em `GameParticipant` + migração

**Files:**
- Modify: `apps/core/models/game_participant.py`
- Create: `apps/core/migrations/0007_*.py` (nome exato gerado pelo Django)

**Interfaces:**
- Produces: `GameParticipant.starting_seat` (int opcional, 1 = primeiro a jogar), `.felt_salty` (bool, default False — marcado por quem **não** venceu), `.fun_rating` (int opcional, 1-5). Consumidos pelas Tasks 2, 6, 8, 9.

- [ ] **Step 1: Implementar**

Em `apps/core/models/game_participant.py`, adicionar o import de validators no topo e os três campos entre `biggest_creature_power` e `created_at`:

```python
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from .game import Game
from .player import Player
from .deck import Deck
from .card import Card


class GameParticipant(models.Model):
    game = models.ForeignKey(
        Game,
        on_delete=models.CASCADE,
        related_name='participants'
    )
    player = models.ForeignKey(
        Player,
        on_delete=models.CASCADE,
        related_name='match_performances'
    )
    deck = models.ForeignKey(
        Deck,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='match_performances'
    )
    placement = models.PositiveSmallIntegerField(
        help_text="Colocação final na partida (1 para Vencedor, etc.)"
    )
    kill_count = models.PositiveIntegerField(default=0)
    mvp_card = models.ForeignKey(
        Card,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mvp_performances',
        help_text="Carta MVP jogada por este participante na partida (opcional)"
    )
    peak_life_total = models.IntegerField(
        null=True, blank=True, help_text="Vida mais alta atingida na partida"
    )
    board_wipes_count = models.PositiveIntegerField(default=0)
    counterspell_count = models.PositiveIntegerField(default=0)
    complaint_count = models.PositiveIntegerField(
        default=0, help_text="Quantas vezes o participante reclamou na partida"
    )
    is_self_elimination = models.BooleanField(
        default=False,
        help_text="O participante foi eliminado por uma ação própria (não por outro jogador)"
    )
    biggest_creature = models.ForeignKey(
        Card,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='biggest_creature_performances',
        help_text="Maior criatura que bateu na mesa nesta partida"
    )
    biggest_creature_power = models.PositiveIntegerField(
        null=True, blank=True, help_text="Poder da criatura alcançado nesta partida"
    )
    starting_seat = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Posição inicial na mesa (1 = primeiro a jogar)"
    )
    felt_salty = models.BooleanField(
        default=False,
        help_text="Marcado por quem NÃO venceu, se achou a vitória do adversário irritante"
    )
    fun_rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="Nota de diversão da partida (1 a 5) dada por este participante"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('game', 'player')
        ordering = ['game', 'placement']

    def __str__(self):
        player_name = self.player.nickname or self.player.name
        return f"{self.game} - {player_name} ({self.placement}º lugar)"
```

- [ ] **Step 2: Gerar migração e verificar**

```bash
.venv/bin/python manage.py makemigrations core
.venv/bin/python manage.py migrate core
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from apps.core.models import GameParticipant
fields = [f.name for f in GameParticipant._meta.get_fields()]
for f in ['starting_seat', 'felt_salty', 'fun_rating']:
    assert f in fields, f
print('campos presentes')
"
```

Esperado: `migrate` sem erro, script imprime `campos presentes`.

- [ ] **Step 3: Commit**

```bash
git add apps/core/models/game_participant.py apps/core/migrations/
git commit -m "Add starting_seat, felt_salty, fun_rating to GameParticipant"
```

### Task 2: Expor os campos novos no admin e no `seed_games`

**Files:**
- Modify: `apps/core/admin.py`
- Modify: `apps/core/management/commands/seed_games.py`

**Interfaces:**
- Consumes: campos da Task 1.

- [ ] **Step 1: Implementar**

Em `apps/core/admin.py`, adicionar os três campos novos em `GameParticipantInline.fields` (depois de `biggest_creature_power`):

```python
    fields = (
        "player",
        "deck",
        "placement",
        "kill_count",
        "mvp_card",
        "peak_life_total",
        "board_wipes_count",
        "counterspell_count",
        "complaint_count",
        "is_self_elimination",
        "biggest_creature",
        "biggest_creature_power",
        "starting_seat",
        "felt_salty",
        "fun_rating",
    )
```

Em `apps/core/management/commands/seed_games.py`, dentro do loop `for idx, (player, deck) in enumerate(valid_participants):`, calcular e passar os três campos novos na criação do `GameParticipant`:

```python
            for idx, (player, deck) in enumerate(valid_participants):
                placement = placements[idx]
                mvp_card = (
                    random.choice(cards) if cards and random.random() > 0.4 else None
                )
                has_biggest_creature = cards and random.random() > 0.7
                biggest_creature = random.choice(cards) if has_biggest_creature else None
                biggest_creature_power = (
                    random.randint(3, 15) if has_biggest_creature else None
                )

                GameParticipant.objects.create(
                    game=game,
                    player=player,
                    deck=deck,
                    placement=placement,
                    kill_count=(
                        random.randint(0, 3) if placement == 1 else random.randint(0, 1)
                    ),
                    mvp_card=mvp_card,
                    peak_life_total=random.choice([None, random.randint(20, 120)]),
                    board_wipes_count=random.choice([0, 0, 0, 1, 2]),
                    counterspell_count=random.choice([0, 0, 1, 2]),
                    complaint_count=random.choice([0, 0, 0, 1, 2, 3]),
                    is_self_elimination=random.random() < 0.05,
                    biggest_creature=biggest_creature,
                    biggest_creature_power=biggest_creature_power,
                    starting_seat=idx + 1,
                    felt_salty=(placement != 1 and random.random() < 0.3),
                    fun_rating=random.choice([None, 2, 3, 4, 4, 5]),
                )
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py seed_games --total 10
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from apps.core.models import GameParticipant
print('com starting_seat:', GameParticipant.objects.exclude(starting_seat__isnull=True).count())
print('com felt_salty=True:', GameParticipant.objects.filter(felt_salty=True).count())
print('com fun_rating:', GameParticipant.objects.exclude(fun_rating__isnull=True).count())
"
```

Esperado: `check` sem issues, `seed_games` roda, e os três contadores são maiores que zero.

- [ ] **Step 3: Commit**

```bash
git add apps/core/admin.py apps/core/management/commands/seed_games.py
git commit -m "Surface starting_seat/felt_salty/fun_rating in admin and seed_games"
```

### Task 3: `DeckDetailUseCase`

**Files:**
- Create: `apps/core/use_cases/deck_detail.py`
- Modify: `apps/core/use_cases/__init__.py`

**Interfaces:**
- Consumes: `Deck`, `Game`, `GameParticipant` (campos da Task 1 inclusos).
- Produces: `DeckDetailUseCase` — `.execute(deck)` retorna dict com `total_games`, `wins`, `win_rate`, `wincon_breakdown` (lista de `{name, count, percentage}`), `matchups` (lista de `{deck, games, opponent_wins, opponent_win_rate}`, ordenada por `opponent_win_rate` decrescente), `arch_enemy` (primeiro item de `matchups` ou `None`), `salt_percentage`, `avg_fun_rating` (ou `None`), `recent_games` (até 10 `Game`, mais recente primeiro). Consumido pela Task 5.

- [ ] **Step 1: Implementar**

Criar `apps/core/use_cases/deck_detail.py`:

```python
from django.db.models import Count

from apps.core.models import Deck, Game, GameParticipant
from apps.shared.use_cases import BaseUseCase


class DeckDetailUseCase(BaseUseCase):
    def perform_request(self, deck: Deck) -> dict:
        performances = GameParticipant.objects.filter(deck=deck).select_related(
            "game", "player"
        )

        total_games = performances.count()
        wins = performances.filter(placement=1).count()
        win_rate = round((wins / total_games * 100), 1) if total_games else 0

        losses = performances.exclude(placement=1)
        salty_count = losses.filter(felt_salty=True).count()
        salt_percentage = (
            round((salty_count / losses.count() * 100), 1) if losses.count() else 0
        )

        fun_ratings = list(
            performances.exclude(fun_rating__isnull=True).values_list(
                "fun_rating", flat=True
            )
        )
        avg_fun_rating = (
            round(sum(fun_ratings) / len(fun_ratings), 1) if fun_ratings else None
        )

        matchups = self._matchups(deck, performances)

        recent_games = (
            Game.objects.filter(participants__deck=deck)
            .distinct()
            .order_by("-date", "-id")[:10]
        )

        return {
            "total_games": total_games,
            "wins": wins,
            "win_rate": win_rate,
            "wincon_breakdown": self._wincon_breakdown(performances),
            "matchups": matchups,
            "arch_enemy": matchups[0] if matchups else None,
            "salt_percentage": salt_percentage,
            "avg_fun_rating": avg_fun_rating,
            "recent_games": recent_games,
        }

    def _wincon_breakdown(self, performances):
        game_ids = performances.filter(placement=1).values_list("game_id", flat=True)
        counts = (
            Game.objects.filter(id__in=game_ids)
            .values("win_condition")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        total = sum(row["count"] for row in counts)
        breakdown = []
        for row in counts:
            pct = round((row["count"] / total * 100), 1) if total else 0
            breakdown.append(
                {"name": row["win_condition"], "count": row["count"], "percentage": pct}
            )
        return breakdown

    def _matchups(self, deck, performances):
        game_ids = list(performances.values_list("game_id", flat=True))
        opponents = (
            GameParticipant.objects.filter(game_id__in=game_ids)
            .exclude(deck=deck)
            .exclude(deck__isnull=True)
            .select_related("deck")
        )

        stats = {}
        for opponent in opponents:
            key = opponent.deck_id
            if key not in stats:
                stats[key] = {"deck": opponent.deck, "games": 0, "opponent_wins": 0}
            stats[key]["games"] += 1
            if opponent.placement == 1:
                stats[key]["opponent_wins"] += 1

        matchups = []
        for row in stats.values():
            opponent_win_rate = round((row["opponent_wins"] / row["games"] * 100), 1)
            matchups.append(
                {
                    "deck": row["deck"],
                    "games": row["games"],
                    "opponent_wins": row["opponent_wins"],
                    "opponent_win_rate": opponent_win_rate,
                }
            )
        matchups.sort(key=lambda row: row["opponent_win_rate"], reverse=True)
        return matchups
```

Atualizar `apps/core/use_cases/__init__.py` (mantendo as entradas existentes):

```python
from .dashboard_stats import DashboardStatsUseCase
from .pod_insights import PodInsightsUseCase
from .player_profile import PlayerProfileUseCase
from .game_detail import GameDetailUseCase
from .deck_detail import DeckDetailUseCase
from .card_image import EnsureCardImageUseCase

__all__ = [
    "DashboardStatsUseCase",
    "PodInsightsUseCase",
    "PlayerProfileUseCase",
    "GameDetailUseCase",
    "DeckDetailUseCase",
    "EnsureCardImageUseCase",
]
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from apps.core.models import Deck
from apps.core.use_cases import DeckDetailUseCase
deck = Deck.objects.first()
data = DeckDetailUseCase().execute(deck)
print(sorted(data.keys()))
print('total_games:', data['total_games'])
"
```

Esperado: chaves =
`['arch_enemy', 'avg_fun_rating', 'matchups', 'recent_games', 'salt_percentage', 'total_games', 'wincon_breakdown', 'win_rate', 'wins']`
(ordem alfabética do `sorted()`), `total_games` inteiro ≥ 0.

- [ ] **Step 3: Commit**

```bash
git add apps/core/use_cases/deck_detail.py apps/core/use_cases/__init__.py
git commit -m "Add DeckDetailUseCase: wincon breakdown, matchups, salt/fun stats"
```

### Task 4: `DeckDetailView` + rota

**Files:**
- Create: `apps/core/views/deck_detail.py`
- Modify: `apps/core/views/__init__.py`
- Modify: `apps/core/urls.py`

**Interfaces:**
- Consumes: `DeckDetailUseCase` (Task 3), `EnsureCardImageUseCase`.
- Produces: rota `core:deck-detail` (`/decks/<int:pk>/`). Contexto ganha `commander_images` (lista de `(Card, url_ou_None)` pra cada comandante do deck).

- [ ] **Step 1: Implementar**

Criar `apps/core/views/deck_detail.py`:

```python
from django.views.generic import DetailView
from apps.core.models import Deck
from apps.core.use_cases import DeckDetailUseCase, EnsureCardImageUseCase


class DeckDetailView(DetailView):
    model = Deck
    template_name = "core/deck_detail.html"
    context_object_name = "deck"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(DeckDetailUseCase().execute(self.object))

        image_use_case = EnsureCardImageUseCase()
        context["commander_images"] = [
            (card, image_use_case.execute(card))
            for card in self.object.commanders.all()
        ]
        return context
```

Atualizar `apps/core/views/__init__.py`:

```python
from .dashboard import DashboardView
from .player_profile import PlayerProfileView
from .player_list import PlayerListView
from .game_list import GameListView
from .game_detail import GameDetailView
from .deck_detail import DeckDetailView

__all__ = [
    "DashboardView",
    "PlayerProfileView",
    "PlayerListView",
    "GameListView",
    "GameDetailView",
    "DeckDetailView",
]
```

Atualizar `apps/core/urls.py`:

```python
from django.urls import path
from apps.core.views import (
    DashboardView,
    DeckDetailView,
    GameDetailView,
    GameListView,
    PlayerListView,
    PlayerProfileView,
)

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("players/", PlayerListView.as_view(), name="player-list"),
    path("players/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
    path("games/", GameListView.as_view(), name="game-list"),
    path("games/<int:pk>/", GameDetailView.as_view(), name="game-detail"),
    path("decks/<int:pk>/", DeckDetailView.as_view(), name="deck-detail"),
]
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python manage.py check
```

Esperado: `System check identified no issues (0 silenced).` (o template ainda não existe — acessar a rota de verdade só funciona depois da Task 5).

- [ ] **Step 3: Commit**

```bash
git add apps/core/views/deck_detail.py apps/core/views/__init__.py apps/core/urls.py
git commit -m "Add DeckDetailView and /decks/<id>/ route"
```

### Task 5: Template `deck_detail.html` + links a partir do dashboard e do perfil

**Files:**
- Create: `apps/core/templates/core/deck_detail.html`
- Modify: `apps/core/templates/core/dashboard.html`
- Modify: `apps/core/templates/core/player_profile.html`

**Interfaces:**
- Consumes: contexto da Task 4.

- [ ] **Step 1: Implementar**

Criar `apps/core/templates/core/deck_detail.html`:

```html
{% extends "base.html" %}

{% block content %}
<div class="space-y-6">

  <button type="button" onclick="history.back()" class="text-sm text-gray-500 hover:text-gray-900 transition">
    ← Voltar
  </button>

  <!-- Hero -->
  <div
    class="relative rounded-xl overflow-hidden border border-gray-200 text-white"
    {% if commander_images.0.1 %}style="background-image: linear-gradient(to right, rgba(17,24,39,0.85), rgba(17,24,39,0.5)), url('{{ commander_images.0.1 }}'); background-size: cover; background-position: center 20%;"{% else %}style="background-color: #111827;"{% endif %}
  >
    <div class="p-8">
      <p class="text-xs font-bold uppercase tracking-wider text-gray-300">Deck de {{ deck.player.name }}</p>
      <h1 class="text-3xl font-bold mt-1">{{ deck.display_commanders|default:"Sem comandante" }}</h1>
      <div class="mt-4 flex flex-wrap items-center gap-8">
        <div>
          <p class="text-3xl font-bold">{{ win_rate }}%</p>
          <p class="text-xs text-gray-300 uppercase tracking-wider">Win Rate</p>
        </div>
        <div>
          <p class="text-3xl font-bold">{{ wins }}</p>
          <p class="text-xs text-gray-300 uppercase tracking-wider">Vitórias</p>
        </div>
        <div>
          <p class="text-3xl font-bold">{{ total_games }}</p>
          <p class="text-xs text-gray-300 uppercase tracking-wider">Partidas</p>
        </div>
        {% if avg_fun_rating %}
        <div>
          <p class="text-3xl font-bold">{{ avg_fun_rating }}/5</p>
          <p class="text-xs text-gray-300 uppercase tracking-wider">Diversão média</p>
        </div>
        {% endif %}
      </div>
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <!-- Wincon breakdown -->
    <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      <div class="p-4 border-b border-gray-100 bg-gray-50/50">
        <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">COMO ESSE DECK GANHA</h2>
      </div>
      <div class="divide-y divide-gray-100">
        {% for row in wincon_breakdown %}
        <div class="p-4 flex items-center justify-between text-sm">
          <span class="font-medium text-gray-700 capitalize">{{ row.name }}</span>
          <span class="text-gray-500">{{ row.count }} vitórias</span>
          <span class="font-bold text-gray-900">{{ row.percentage }}%</span>
        </div>
        {% empty %}
        <div class="p-4 text-center text-xs text-gray-400">Esse deck ainda não venceu.</div>
        {% endfor %}
      </div>
    </div>

    <!-- Clima na mesa -->
    <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      <div class="p-4 border-b border-gray-100 bg-gray-50/50">
        <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">CLIMA NA MESA</h2>
      </div>
      <div class="divide-y divide-gray-100 text-sm">
        <div class="p-4 flex items-center justify-between">
          <span class="text-gray-500">🧂 Achado "salgado" pelos adversários</span>
          <span class="font-bold text-gray-900">{{ salt_percentage }}%</span>
        </div>
        <div class="p-4 flex items-center justify-between">
          <span class="text-gray-500">Nota média de diversão</span>
          <span class="font-bold text-gray-900">{% if avg_fun_rating %}{{ avg_fun_rating }}/5{% else %}-{% endif %}</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Matchups -->
  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="p-4 border-b border-gray-100 bg-gray-50/50 flex items-center justify-between">
      <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">CONFRONTOS DIRETOS</h2>
      {% if arch_enemy %}<span class="text-xs text-gray-400">Arqui-inimigo: {{ arch_enemy.deck.display_commanders }}</span>{% endif %}
    </div>
    <div class="divide-y divide-gray-100">
      {% for row in matchups %}
      <div class="p-4 flex items-center justify-between text-sm">
        <a href="{% url 'core:deck-detail' row.deck.id %}" class="font-medium text-gray-700 hover:underline">{{ row.deck.display_commanders }}</a>
        <span class="text-gray-500">{{ row.games }} partidas juntos</span>
        <span class="font-bold text-gray-900">{{ row.opponent_win_rate }}% de vitória deles</span>
      </div>
      {% empty %}
      <div class="p-4 text-center text-xs text-gray-400">Ainda não enfrentou nenhum outro comandante.</div>
      {% endfor %}
    </div>
  </div>

  <!-- Partidas recentes -->
  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="p-4 border-b border-gray-100 bg-gray-50/50">
      <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">PARTIDAS RECENTES</h2>
    </div>
    <div class="divide-y divide-gray-100">
      {% for game in recent_games %}
      <a href="{% url 'core:game-detail' game.id %}" class="p-4 flex items-center justify-between text-sm hover:bg-gray-50/50 transition">
        <span class="text-gray-700">{{ game.date|date:"d/m/Y"|default:"Sem data" }}</span>
        <span class="text-gray-500 capitalize">{{ game.win_condition|default:"-" }}</span>
      </a>
      {% empty %}
      <div class="p-4 text-center text-xs text-gray-400">Nenhuma partida registrada ainda.</div>
      {% endfor %}
    </div>
  </div>

</div>
{% endblock %}
```

Em `apps/core/templates/core/dashboard.html`, dentro do bloco "Top comandantes qualificados" (dentro do `<details>` de `TOP COMANDANTES`), trocar:

```html
            <span class="font-medium text-gray-700">{{ row.deck.display_commanders }}</span>
```
por:
```html
            <a href="{% url 'core:deck-detail' row.deck.id %}" class="font-medium text-gray-700 hover:underline">{{ row.deck.display_commanders }}</a>
```

Em `apps/core/templates/core/player_profile.html`, no bloco "COMANDANTES PILOTADOS", trocar o `<div class="flex items-center gap-1 font-medium text-gray-700">` externo por um link, mantendo os `<span data-card-image>` internos intactos:

```html
        <a href="{% url 'core:deck-detail' row.deck.id %}" class="flex items-center gap-1 font-medium text-gray-700 hover:underline">
          {% for card, image_url in row.commander_images %}
          <span
            class="{% if image_url %}cursor-zoom-in{% endif %}"
            {% if image_url %}data-card-image="{{ image_url }}"{% endif %}
          >{{ card.name }}</span>{% if not forloop.last %} /{% endif %}
          {% empty %}
          <span>Sem comandante</span>
          {% endfor %}
        </a>
```

(o link inteiro já fica sublinhado no hover via `hover:underline` no `<a>`, então tirei o `hover:underline decoration-dotted` individual de cada `<span>` pra não duplicar sublinhado)

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from django.test import Client
from django.test.utils import setup_test_environment
from apps.core.models import Deck
setup_test_environment()
c = Client()
deck = Deck.objects.first()
print('deck detail:', c.get(f'/decks/{deck.id}/').status_code)
print('dashboard:', c.get('/').status_code)
player_id = deck.player_id
print('player profile:', c.get(f'/players/{player_id}/').status_code)
"
```

Esperado: as três rotas retornam `200`.

- [ ] **Step 3: Commit**

```bash
git add apps/core/templates/core/deck_detail.html apps/core/templates/core/dashboard.html apps/core/templates/core/player_profile.html
git commit -m "Add deck detail template and link to it from dashboard/profile"
```

### Task 6: Filtro de janela de tempo + posição na mesa em `PodInsightsUseCase`/`DashboardStatsUseCase`

**Files:**
- Modify: `apps/core/use_cases/dashboard_stats.py`
- Modify: `apps/core/use_cases/pod_insights.py`

**Interfaces:**
- Produces: `DashboardStatsUseCase.execute(since=None)` e `PodInsightsUseCase.execute(since=None)` — `since` é uma `date` opcional; quando presente, filtra os `Game`/`GameParticipant` considerados (exceto `records`, que continua all-time). `PodInsightsUseCase` ganha a chave nova `seat_stats` (lista de `{seat, games, wins, win_rate}`). Consumido pela Task 7.

- [ ] **Step 1: Implementar**

Reescrever `apps/core/use_cases/dashboard_stats.py` inteiro:

```python
from django.db.models import Count
from apps.core.models import Achievement, Deck, Game, GameParticipant, Player
from apps.shared.use_cases import BaseUseCase


class DashboardStatsUseCase(BaseUseCase):
    def perform_request(self, since=None) -> dict:
        games = Game.objects.all()
        achievements_qs = Achievement.objects.select_related("player")
        participants = GameParticipant.objects.all()
        if since:
            games = games.filter(date__gte=since)
            achievements_qs = achievements_qs.filter(date__gte=since)
            participants = participants.filter(game__date__gte=since)

        total_games = games.count()
        total_decks = Deck.objects.filter(is_active=True).count()

        ranked_players = []
        for player in Player.objects.all():
            performances = player.match_performances.all()
            if since:
                performances = performances.filter(game__date__gte=since)
            total = performances.count()
            wins = performances.filter(placement=1).count()
            wr = round((wins / total * 100), 1) if total else 0
            ranked_players.append(
                {
                    "id": player.id,
                    "name": player.name,
                    "wins": wins,
                    "total_games": total,
                    "win_rate": wr,
                }
            )
        ranked_players.sort(key=lambda p: (-p["wins"], -p["total_games"]))

        top_player = (
            ranked_players[0]
            if ranked_players and ranked_players[0]["total_games"]
            else None
        )

        wincon_counts = (
            games.values("win_condition").annotate(count=Count("id")).order_by("-count")
        )

        wincon_modes = []
        for wc in wincon_counts:
            pct = round((wc["count"] / total_games * 100), 1) if total_games > 0 else 0
            wincon_modes.append(
                {"name": wc["win_condition"], "count": wc["count"], "percentage": pct}
            )

        top_wincon = wincon_modes[0] if wincon_modes else None

        top_mvp_query = (
            participants.filter(mvp_card__isnull=False)
            .values("mvp_card", "mvp_card__name")
            .annotate(count=Count("id"))
            .order_by("-count")
            .first()
        )
        top_mvp = (
            {"id": top_mvp_query["mvp_card"], "name": top_mvp_query["mvp_card__name"]}
            if top_mvp_query
            else None
        )

        achievements = achievements_qs.order_by("-date", "-id")[:5]

        return {
            "total_games": total_games,
            "total_decks": total_decks,
            "top_player": top_player,
            "top_wincon": top_wincon,
            "top_mvp": top_mvp,
            "ranked_players": ranked_players,
            "wincon_modes": wincon_modes,
            "achievements": achievements,
        }
```

Em `apps/core/use_cases/pod_insights.py`, reescrever o arquivo inteiro:

```python
from django.db.models import Count
from django.db.models.functions import TruncMonth

from apps.core.models import Deck, Game, GameParticipant, Player
from apps.shared.use_cases import BaseUseCase

POINTS_BY_PLACEMENT = {1: 4, 2: 2, 3: 1}


class PodInsightsUseCase(BaseUseCase):
    def perform_request(self, since=None) -> dict:
        return {
            "color_identity_stats": self._color_identity_stats(since),
            "color_count_stats": self._color_count_stats(since),
            "wincon_trend": self._wincon_trend(since),
            "points_ranking": self._points_ranking(since),
            "top_commanders_qualified": self._top_commanders_qualified(since),
            "seat_stats": self._seat_stats(since),
            "records": self._records(),
        }

    def _color_identity_stats(self, since):
        stats = []
        for color in "WUBRG":
            decks_with_color = Deck.objects.filter(color_identity__contains=color)
            performances = GameParticipant.objects.filter(deck__in=decks_with_color)
            if since:
                performances = performances.filter(game__date__gte=since)
            games = performances.count()
            wins = performances.filter(placement=1).count()
            win_rate = round((wins / games * 100), 1) if games else 0
            stats.append(
                {"color": color, "games": games, "wins": wins, "win_rate": win_rate}
            )
        return stats

    def _color_count_stats(self, since):
        buckets = {n: {"games": 0, "wins": 0} for n in range(6)}
        for deck in Deck.objects.all():
            performances = deck.match_performances.all()
            if since:
                performances = performances.filter(game__date__gte=since)
            games = performances.count()
            wins = performances.filter(placement=1).count()
            num_colors = (
                0 if deck.color_identity in ("", "C") else len(deck.color_identity)
            )
            buckets[num_colors]["games"] += games
            buckets[num_colors]["wins"] += wins

        stats = []
        for num_colors, totals in sorted(buckets.items()):
            games = totals["games"]
            wins = totals["wins"]
            win_rate = round((wins / games * 100), 1) if games else 0
            stats.append(
                {
                    "colors": num_colors,
                    "games": games,
                    "wins": wins,
                    "win_rate": win_rate,
                }
            )
        return stats

    def _wincon_trend(self, since):
        games = Game.objects.exclude(date__isnull=True)
        if since:
            games = games.filter(date__gte=since)
        trend = (
            games.annotate(month=TruncMonth("date"))
            .values("month", "win_condition")
            .annotate(count=Count("id"))
            .order_by("month", "win_condition")
        )
        return list(trend)

    def _points_ranking(self, since):
        ranking = []
        for player in Player.objects.all():
            performances = player.match_performances.all()
            if since:
                performances = performances.filter(game__date__gte=since)
            points = sum(
                POINTS_BY_PLACEMENT.get(p.placement, 0) for p in performances
            )
            ranking.append({"player": player, "points": points})
        ranking.sort(key=lambda row: row["points"], reverse=True)
        return ranking

    def _top_commanders_qualified(self, since):
        qualified = []
        for deck in Deck.objects.all():
            performances = deck.match_performances.all()
            if since:
                performances = performances.filter(game__date__gte=since)
            games = performances.count()
            if games < 5:
                continue
            wins = performances.filter(placement=1).count()
            win_rate = round((wins / games * 100), 1)
            if win_rate >= 20:
                qualified.append(
                    {"deck": deck, "games": games, "wins": wins, "win_rate": win_rate}
                )
        qualified.sort(key=lambda row: row["win_rate"], reverse=True)
        return qualified

    def _seat_stats(self, since):
        performances = GameParticipant.objects.exclude(starting_seat__isnull=True)
        if since:
            performances = performances.filter(game__date__gte=since)

        buckets = {}
        for performance in performances:
            seat = performance.starting_seat
            buckets.setdefault(seat, {"games": 0, "wins": 0})
            buckets[seat]["games"] += 1
            if performance.placement == 1:
                buckets[seat]["wins"] += 1

        stats = []
        for seat, totals in sorted(buckets.items()):
            win_rate = round((totals["wins"] / totals["games"] * 100), 1)
            stats.append(
                {
                    "seat": seat,
                    "games": totals["games"],
                    "wins": totals["wins"],
                    "win_rate": win_rate,
                }
            )
        return stats

    def _records(self):
        def top_by(field):
            obj = (
                GameParticipant.objects.select_related("player", "game")
                .order_by(f"-{field}")
                .first()
            )
            return obj if obj and getattr(obj, field) > 0 else None

        most_life = (
            GameParticipant.objects.select_related("player", "game")
            .exclude(peak_life_total__isnull=True)
            .order_by("-peak_life_total")
            .first()
        )
        biggest_creature = (
            GameParticipant.objects.select_related("player", "game", "biggest_creature")
            .exclude(biggest_creature__isnull=True)
            .order_by("-biggest_creature_power")
            .first()
        )
        fastest_game_no_combo = (
            Game.objects.exclude(win_condition="combo")
            .exclude(turn_count__isnull=True)
            .order_by("turn_count")
            .first()
        )
        fastest_game_combo = (
            Game.objects.filter(win_condition="combo")
            .exclude(turn_count__isnull=True)
            .order_by("turn_count")
            .first()
        )

        return {
            "board_wipes": top_by("board_wipes_count"),
            "counterspells": top_by("counterspell_count"),
            "complaints": top_by("complaint_count"),
            "most_life": most_life,
            "biggest_creature": biggest_creature,
            "self_eliminations_count": GameParticipant.objects.filter(
                is_self_elimination=True
            ).count(),
            "fastest_game_no_combo": fastest_game_no_combo,
            "fastest_game_combo": fastest_game_combo,
            "saltiest_deck": self._saltiest_deck(),
            "most_fun_deck": self._most_fun_deck(),
        }

    def _saltiest_deck(self):
        best = None
        for deck in Deck.objects.all():
            wins = GameParticipant.objects.filter(deck=deck, placement=1)
            if wins.count() < 3:
                continue
            salty_reactions = 0
            eligible_reactions = 0
            for win in wins:
                opponents = GameParticipant.objects.filter(game=win.game).exclude(
                    placement=1
                )
                eligible_reactions += opponents.count()
                salty_reactions += opponents.filter(felt_salty=True).count()
            if eligible_reactions == 0:
                continue
            salt_percentage = round((salty_reactions / eligible_reactions * 100), 1)
            if best is None or salt_percentage > best["salt_percentage"]:
                best = {"deck": deck, "salt_percentage": salt_percentage}
        return best

    def _most_fun_deck(self):
        best = None
        for deck in Deck.objects.all():
            ratings = list(
                GameParticipant.objects.filter(deck=deck)
                .exclude(fun_rating__isnull=True)
                .values_list("fun_rating", flat=True)
            )
            if len(ratings) < 3:
                continue
            avg_rating = round(sum(ratings) / len(ratings), 1)
            if best is None or avg_rating > best["avg_rating"]:
                best = {"deck": deck, "avg_rating": avg_rating}
        return best
```

`_saltiest_deck`/`_most_fun_deck` exigem pelo menos 3 amostras (3 vitórias, ou 3 notas de diversão) pra virar "recorde" — evita que uma única partida isolada corone um deck, mesma lógica de "amostra mínima" que `_top_commanders_qualified` já usa (lá é ≥5 jogos).

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from datetime import date, timedelta
from apps.core.use_cases import DashboardStatsUseCase, PodInsightsUseCase

data_all = DashboardStatsUseCase().execute()
data_7d = DashboardStatsUseCase().execute(since=date.today() - timedelta(days=7))
print('total_games all:', data_all['total_games'], '| 7d:', data_7d['total_games'])
assert data_7d['total_games'] <= data_all['total_games']

insights = PodInsightsUseCase().execute()
print(sorted(insights.keys()))
print('seat_stats:', insights['seat_stats'])
print('records keys:', sorted(insights['records'].keys()))
"
```

Esperado: `total_games` da janela de 7 dias é menor ou igual ao total geral; `seat_stats` é uma lista (pode ser vazia se `seed_games` não tiver rodado depois da Task 2); `records keys` inclui `saltiest_deck` e `most_fun_deck` além das chaves já existentes.

- [ ] **Step 3: Commit**

```bash
git add apps/core/use_cases/dashboard_stats.py apps/core/use_cases/pod_insights.py
git commit -m "Add since-window filtering, seat stats, and salt/fun records"
```

### Task 7: `DashboardView` lê `?days=` + template (botões de janela + seção de posição na mesa)

**Files:**
- Modify: `apps/core/views/dashboard.py`
- Modify: `apps/core/templates/core/dashboard.html`

**Interfaces:**
- Consumes: `DashboardStatsUseCase`/`PodInsightsUseCase` com `since` (Task 6).
- Produces: `context["active_window"]` (`""`, `"7"` ou `"30"`), usado pelo template pra destacar o botão ativo.

- [ ] **Step 1: Implementar**

Reescrever `apps/core/views/dashboard.py`:

```python
from datetime import timedelta

from django.utils import timezone
from django.views.generic import TemplateView
from apps.core.models import Card
from apps.core.use_cases import (
    DashboardStatsUseCase,
    EnsureCardImageUseCase,
    PodInsightsUseCase,
)

WINDOW_DAYS = {"7": 7, "30": 30}


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        window = self.request.GET.get("days")
        days = WINDOW_DAYS.get(window)
        since = timezone.now().date() - timedelta(days=days) if days else None

        context.update(DashboardStatsUseCase().execute(since=since))
        context.update(PodInsightsUseCase().execute(since=since))
        context["active_window"] = window if window in WINDOW_DAYS else ""

        top_mvp = context.get("top_mvp")
        if top_mvp:
            card = Card.objects.filter(pk=top_mvp["id"]).first()
            top_mvp["image_url"] = (
                EnsureCardImageUseCase().execute(card) if card else None
            )

        return context
```

Em `apps/core/templates/core/dashboard.html`, trocar o bloco do cabeçalho (que hoje é só o `<h1>`/`<p>`) por uma versão com os botões de janela de tempo ao lado:

```html
  <div class="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
    <div>
      <h1 class="text-2xl font-bold text-gray-900">Overview do Pod</h1>
      <p class="text-sm text-gray-500">Estatísticas acumuladas de partidas de Commander/EDH.</p>
    </div>
    <div class="flex items-center gap-2 text-xs font-medium">
      <a href="?" class="px-3 py-1.5 rounded-md border {% if not active_window %}bg-gray-900 text-white border-gray-900{% else %}text-gray-600 border-gray-200 hover:border-gray-400{% endif %}">Sempre</a>
      <a href="?days=30" class="px-3 py-1.5 rounded-md border {% if active_window == '30' %}bg-gray-900 text-white border-gray-900{% else %}text-gray-600 border-gray-200 hover:border-gray-400{% endif %}">30 dias</a>
      <a href="?days=7" class="px-3 py-1.5 rounded-md border {% if active_window == '7' %}bg-gray-900 text-white border-gray-900{% else %}text-gray-600 border-gray-200 hover:border-gray-400{% endif %}">7 dias</a>
    </div>
  </div>
```

Dentro do grupo "Mais Estatísticas" (mesmo bloco `<div class="space-y-3">` onde já estão os `<details>` de Pontuação/Win Rate/Top Comandantes/Wincon por Mês/Recordes), adicionar um novo `<details>` pra posição na mesa, logo depois do de "WIN RATE POR COR":

```html
      <!-- Win rate por posição na mesa -->
      <details class="group bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        <summary class="p-4 bg-gray-50/50 flex items-center justify-between cursor-pointer list-none select-none">
          <h3 class="text-xs font-bold text-gray-900 uppercase tracking-wider">WIN RATE POR POSIÇÃO NA MESA</h3>
          <span class="text-gray-400 transition-transform group-open:rotate-180">▾</span>
        </summary>
        <div class="divide-y divide-gray-100 border-t border-gray-100">
          {% for row in seat_stats %}
          <div class="p-4 flex items-center justify-between text-sm">
            <span class="font-medium text-gray-700">Posição {{ row.seat }}</span>
            <span class="text-gray-500">{{ row.games }} jogos</span>
            <span class="font-bold text-gray-900">{{ row.win_rate }}%</span>
          </div>
          {% empty %}
          <div class="p-4 text-center text-xs text-gray-400">Nenhuma partida com posição inicial registrada ainda.</div>
          {% endfor %}
        </div>
      </details>
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from django.test import Client
from django.test.utils import setup_test_environment
setup_test_environment()
c = Client()
print('sempre:', c.get('/').status_code)
print('30 dias:', c.get('/?days=30').status_code)
print('7 dias:', c.get('/?days=7').status_code)
"
```

Esperado: as três variações retornam `200`.

- [ ] **Step 3: Commit**

```bash
git add apps/core/views/dashboard.py apps/core/templates/core/dashboard.html
git commit -m "Add dashboard time-window filter and seat position stats section"
```

### Task 8: Recordes de salt e diversão no dashboard

**Files:**
- Modify: `apps/core/templates/core/dashboard.html`

**Interfaces:**
- Consumes: `records.saltiest_deck`/`records.most_fun_deck` (Task 6).

- [ ] **Step 1: Implementar**

Dentro do `<details>` de "RECORDES DO POD", adicionar duas linhas novas ao final (antes do `</div></details>` de fechamento):

```html
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">🧂 Deck mais "salgado" (min. 3 vitórias)</span>
        {% if records.saltiest_deck %}
        <a href="{% url 'core:deck-detail' records.saltiest_deck.deck.id %}" class="font-semibold text-gray-900 hover:underline">
          {{ records.saltiest_deck.deck.display_commanders }} ({{ records.saltiest_deck.salt_percentage }}%)
        </a>
        {% else %}<span class="text-gray-400">-</span>{% endif %}
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Deck mais divertido (min. 3 notas)</span>
        {% if records.most_fun_deck %}
        <a href="{% url 'core:deck-detail' records.most_fun_deck.deck.id %}" class="font-semibold text-gray-900 hover:underline">
          {{ records.most_fun_deck.deck.display_commanders }} ({{ records.most_fun_deck.avg_rating }}/5)
        </a>
        {% else %}<span class="text-gray-400">-</span>{% endif %}
      </div>
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from django.test import Client
from django.test.utils import setup_test_environment
setup_test_environment()
c = Client()
resp = c.get('/')
print('status:', resp.status_code)
"
```

Esperado: `status: 200`.

- [ ] **Step 3: Commit**

```bash
git add apps/core/templates/core/dashboard.html
git commit -m "Show saltiest and most fun deck in dashboard records"
```

### Task 9: Sparkline de tendência de win rate no perfil do jogador

**Files:**
- Modify: `apps/core/use_cases/player_profile.py`
- Modify: `apps/core/templates/core/player_profile.html`

**Interfaces:**
- Produces: `PlayerProfileUseCase.execute(player)` ganha a chave `win_rate_trend` (dict com `points` — lista de `{month, win_rate}` — e `svg_points`, a string pronta pro atributo `points` de um `<polyline>` SVG, viewBox `0 0 280 60`).

- [ ] **Step 1: Implementar**

Em `apps/core/use_cases/player_profile.py`, adicionar o import de `TruncMonth` e `Count`/`Q` (já tem `Count, Q`), e um método novo `_win_rate_trend`, chamado em `perform_request`:

```python
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth

from apps.core.models import Deck, Player
from apps.core.use_cases.pod_insights import POINTS_BY_PLACEMENT
from apps.shared.use_cases import BaseUseCase


class PlayerProfileUseCase(BaseUseCase):
    def perform_request(self, player: Player) -> dict:
        performances = player.match_performances.select_related(
            "game", "deck", "biggest_creature"
        )

        total_games = performances.count()
        wins = performances.filter(placement=1).count()
        win_rate = round((wins / total_games * 100), 1) if total_games else 0
        points = sum(POINTS_BY_PLACEMENT.get(p.placement, 0) for p in performances)

        decks = (
            Deck.objects.filter(player=player)
            .prefetch_related("commanders")
            .annotate(
                deck_games=Count("match_performances"),
                deck_wins=Count(
                    "match_performances",
                    filter=Q(match_performances__placement=1),
                ),
            )
        )
        commander_stats = []
        for deck in decks:
            deck_win_rate = (
                round((deck.deck_wins / deck.deck_games * 100), 1)
                if deck.deck_games
                else 0
            )
            commander_stats.append(
                {
                    "deck": deck,
                    "games": deck.deck_games,
                    "wins": deck.deck_wins,
                    "win_rate": deck_win_rate,
                }
            )

        def top_by(field):
            obj = performances.order_by(f"-{field}").first()
            return obj if obj and getattr(obj, field) > 0 else None

        records = {
            "board_wipes": top_by("board_wipes_count"),
            "counterspells": top_by("counterspell_count"),
            "complaints": top_by("complaint_count"),
            "most_life": performances.exclude(peak_life_total__isnull=True)
            .order_by("-peak_life_total")
            .first(),
            "biggest_creature": performances.exclude(biggest_creature__isnull=True)
            .order_by("-biggest_creature_power")
            .first(),
        }

        return {
            "total_games": total_games,
            "wins": wins,
            "win_rate": win_rate,
            "points": points,
            "commander_stats": commander_stats,
            "records": records,
            "win_rate_trend": self._win_rate_trend(performances),
        }

    def _win_rate_trend(self, performances):
        monthly = (
            performances.exclude(game__date__isnull=True)
            .annotate(month=TruncMonth("game__date"))
            .values("month")
            .annotate(total=Count("id"), wins=Count("id", filter=Q(placement=1)))
            .order_by("month")
        )
        data = []
        for row in monthly:
            win_rate = round((row["wins"] / row["total"] * 100), 1) if row["total"] else 0
            data.append({"month": row["month"], "win_rate": win_rate})
        return {"points": data, "svg_points": self._build_svg_points(data)}

    def _build_svg_points(self, points):
        if len(points) < 2:
            return ""
        width, height = 280, 60
        step = width / (len(points) - 1)
        coords = []
        for i, point in enumerate(points):
            x = round(i * step, 1)
            y = round(height - (point["win_rate"] / 100 * height), 1)
            coords.append(f"{x},{y}")
        return " ".join(coords)
```

Em `apps/core/templates/core/player_profile.html`, adicionar uma seção nova logo depois do card "COMANDANTES PILOTADOS" e antes de "RECORDES PESSOAIS":

```html
  {% if win_rate_trend.svg_points %}
  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="p-4 border-b border-gray-100 bg-gray-50/50">
      <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">TENDÊNCIA DE WIN RATE</h2>
    </div>
    <div class="p-4">
      <svg viewBox="0 0 280 60" class="w-full h-16" preserveAspectRatio="none">
        <polyline
          points="{{ win_rate_trend.svg_points }}"
          fill="none"
          stroke="#4f46e5"
          stroke-width="2"
          stroke-linecap="round"
          stroke-linejoin="round"
        />
      </svg>
    </div>
  </div>
  {% endif %}
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from apps.core.models import Player
from apps.core.use_cases import PlayerProfileUseCase
player = Player.objects.first()
data = PlayerProfileUseCase().execute(player)
print('win_rate_trend keys:', sorted(data['win_rate_trend'].keys()))
print('svg_points:', data['win_rate_trend']['svg_points'])
"
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from django.test import Client
from django.test.utils import setup_test_environment
from apps.core.models import Player
setup_test_environment()
c = Client()
player = Player.objects.first()
resp = c.get(f'/players/{player.id}/')
print('status:', resp.status_code)
"
```

Esperado: `win_rate_trend keys: ['points', 'svg_points']`, `svg_points` é uma string vazia (se o jogador só tem partidas num único mês) ou uma lista de coordenadas tipo `"0,12.0 280.0,45.2"`; `status: 200`.

- [ ] **Step 3: Commit**

```bash
git add apps/core/use_cases/player_profile.py apps/core/templates/core/player_profile.html
git commit -m "Add server-rendered SVG win-rate trend sparkline to player profile"
```

---

## Verificação final (depois de todas as tasks)

```bash
.venv/bin/python manage.py check
.venv/bin/python manage.py makemigrations --check --dry-run
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from django.test import Client
from django.test.utils import setup_test_environment
from apps.core.models import Deck, Game, Player
setup_test_environment()
c = Client()
deck = Deck.objects.first()
game = Game.objects.first()
player = Player.objects.first()
print('/                ->', c.get('/').status_code)
print('/?days=7         ->', c.get('/?days=7').status_code)
print(f'/decks/{deck.id}/    ->', c.get(f'/decks/{deck.id}/').status_code)
print(f'/games/{game.id}/    ->', c.get(f'/games/{game.id}/').status_code)
print(f'/players/{player.id}/  ->', c.get(f'/players/{player.id}/').status_code)
"
```

Esperado: `check` sem issues, `makemigrations --check` sem diffs pendentes, todas as rotas retornando `200`. Depois, subir o servidor de verdade (`preview_start` com o launch config `django` já criado em `.claude/launch.json`) e conferir visualmente: hero banner do deck, botões de janela de tempo no dashboard, seção de posição na mesa, recordes de salt/diversão, e o sparkline no perfil.
