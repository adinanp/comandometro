# Pod Metrics, Novas Telas, Admin Oculto e Imagens do Scryfall Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implementar as 4 frentes aprovadas no spec (`docs/superpowers/specs/2026-08-28-pod-metrics-platform-expansion-design.md`): novas métricas estruturadas de partida, três telas novas (perfil do jogador, lista e detalhe de partidas), admin oculto atrás de uma rota configurável, e imagens de cartas via Scryfall.

**Architecture:** Django idiomático — campos novos direto em `Game`/`GameParticipant` (sem tabela EAV), use cases (`BaseUseCase`) por tela/responsabilidade em `apps/core/use_cases/`, views finas que só chamam use cases e montam contexto, templates seguindo o estilo Tailwind já usado em `dashboard.html`.

**Tech Stack:** Django 6.1, django-environ, Tailwind (CDN), Scryfall REST API (`urllib`, sem dependência nova).

## Global Constraints

- Este projeto **não tem suite de testes automatizados** (decisão explícita do usuário) — cada tarefa é verificada com `manage.py check`, um comando `manage.py shell -c "..."` (ou script Python via `.venv/bin/python -c`), ou o `Client` de teste do Django (`django.test.Client` + `setup_test_environment()`), nunca com `pytest`.
- Usar sempre `.venv/bin/python` (não `python`/`python3` do shell) — o venv do projeto é quem tem Django instalado.
- Seguir a convenção de pacote de arquivos já estabelecida: um use case por módulo em `apps/core/use_cases/`, reexportado em `__init__.py`; uma view por módulo em `apps/core/views/`, idem.
- Todo use case herda de `apps.shared.use_cases.BaseUseCase` e implementa `perform_request()`.
- Sem migração de dados históricos — campos novos ficam `null`/`0` em partidas antigas; recordes computados simplesmente ignoram valores vazios.
- Sem download/armazenamento local de imagens — só cache da URL do Scryfall (hotlink).
- Commits pequenos, um por tarefa, seguindo o estilo de mensagem já usado no histórico do repo (`git log --oneline`).

---

## Parte A — Esconder o Admin

### Task 1: Rota de admin configurável via env + remoção do link público

**Files:**
- Modify: `config/settings/base.py` (perto de `ALLOWED_HOSTS`)
- Modify: `config/urls.py` (arquivo inteiro — hoje tem um import duplicado de `path` que também será limpo)
- Modify: `.env.example`
- Modify: `templates/base.html`

**Interfaces:**
- Produces: `settings.ADMIN_URL` (string, ex: `"pod-cmd-7f2a9d/"`), consumida só por `config/urls.py`.

- [ ] **Step 1: Implementar**

Em `config/settings/base.py`, logo abaixo da linha `ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])`:

```python
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

ADMIN_URL = env("ADMIN_URL", default="pod-cmd-7f2a9d/")
```

Reescrever `config/urls.py` inteiro (remove o import duplicado de `path` e troca a rota fixa `admin/` pela variável):

```python
"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include(("apps.core.urls", "core"), namespace="core")),
]
```

Em `.env.example`, adicionar a linha `ADMIN_URL=` no final (vazio — o default obscuro já vive no código, isso só documenta que a variável existe):

```
DATABASE_URL=postgres://user:password@localhost:5432/comandometro
DJANGO_SETTINGS_MODULE=config.settings.local
SECRET_KEY=change-me
ALLOWED_HOSTS=
ADMIN_URL=
```

Em `templates/base.html`, trocar o bloco da nav (remove o link `/admin/`; o link "Partidas" será adicionado numa tarefa mais adiante, por enquanto só sobra o Dashboard):

```html
        <nav class="flex items-center gap-6 text-sm font-medium text-gray-600">
          <a
            href="{% url 'core:dashboard' %}"
            class="text-gray-900 font-semibold"
            >Dashboard</a
          >
        </nav>
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from django.conf import settings
from django.test import Client
from django.test.utils import setup_test_environment
setup_test_environment()
c = Client()
print('ADMIN_URL:', settings.ADMIN_URL)
print('/admin/ status:', c.get('/admin/').status_code)
print('new path status:', c.get('/' + settings.ADMIN_URL).status_code)
"
grep -rn "/admin/" templates/ apps/core/templates/ || echo "nenhuma referência a /admin/ nos templates"
```

Esperado: `/admin/ status: 404`, `new path status: 302` (redireciona pro login do admin), e o grep não deve retornar nenhuma linha (a mensagem "nenhuma referência..." deve aparecer).

- [ ] **Step 3: Commit**

```bash
git add config/settings/base.py config/urls.py .env.example templates/base.html
git commit -m "Hide admin behind env-driven ADMIN_URL and drop public admin link"
```

---

## Parte B — Imagens do Scryfall

### Task 2: Campos `scryfall_id` e `image_url` em `Card`

**Files:**
- Modify: `apps/core/models/card.py`
- Create: `apps/core/migrations/0004_card_scryfall_id_image_url.py` (nome exato gerado pelo Django pode variar — rode `makemigrations` e confirme o arquivo criado)

**Interfaces:**
- Produces: `Card.scryfall_id` (str, pode ser vazio), `Card.image_url` (str/URL, pode ser vazio) — consumidos pela Task 3 e Task 4.

- [ ] **Step 1: Implementar**

Em `apps/core/models/card.py`, adicionar os dois campos novos entre `is_partner_eligible` e `created_at`:

```python
from django.db import models


class Card(models.Model):
    name = models.CharField(max_length=255, unique=True)
    color_identity = models.CharField(max_length=10, blank=True)
    mana_value = models.PositiveIntegerField(
        default=0, help_text="Valor de mana convertido (CMC)"
    )
    is_commander_eligible = models.BooleanField(default=False)
    is_partner_eligible = models.BooleanField(default=False)
    scryfall_id = models.CharField(max_length=36, blank=True)
    image_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
```

- [ ] **Step 2: Gerar migração e verificar**

```bash
.venv/bin/python manage.py makemigrations core
.venv/bin/python manage.py migrate core
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from apps.core.models import Card
print('scryfall_id' in [f.name for f in Card._meta.get_fields()])
print('image_url' in [f.name for f in Card._meta.get_fields()])
"
```

Esperado: `makemigrations` cria um arquivo novo em `apps/core/migrations/` (anote o nome exato pra usar no `git add`), `migrate` roda sem erro, e o script imprime `True` duas vezes.

- [ ] **Step 3: Commit**

```bash
git add apps/core/models/card.py apps/core/migrations/
git commit -m "Add scryfall_id and image_url fields to Card"
```

### Task 3: `import_mtgjson.py` captura o `scryfall_id`

**Files:**
- Modify: `apps/core/management/commands/import_mtgjson.py`

**Interfaces:**
- Consumes: `Card.scryfall_id` (Task 2)
- Produces: cada `Card` criado/atualizado pelo comando passa a ter `scryfall_id` preenchido a partir de `identifiers.scryfallId` do payload do MTGJSON.

- [ ] **Step 1: Implementar**

Dentro do loop `for card_name, printings in cards_data.items():`, logo depois da leitura de `raw_mana_value`/`mana_value`, extrair o `scryfall_id`:

```python
            # Tratamento seguro para manaValue (previne overflow com cartas como Gleemax)
            raw_mana_value = card_info.get("manaValue", 0)
            try:
                mana_value = min(int(float(raw_mana_value)), 999)
            except (ValueError, TypeError):
                mana_value = 0

            identifiers = card_info.get("identifiers", {})
            scryfall_id = identifiers.get("scryfallId", "")

            if card_name in existing_cards:
                obj = existing_cards[card_name]
                obj.color_identity = color_identity
                obj.mana_value = mana_value
                obj.is_commander_eligible = is_commander_eligible
                obj.is_partner_eligible = is_partner_eligible
                obj.scryfall_id = scryfall_id
                cards_to_update.append(obj)
            else:
                cards_to_create.append(
                    Card(
                        name=card_name,
                        color_identity=color_identity,
                        mana_value=mana_value,
                        is_commander_eligible=is_commander_eligible,
                        is_partner_eligible=is_partner_eligible,
                        scryfall_id=scryfall_id,
                    )
                )
```

E no `bulk_update`, adicionar `"scryfall_id"` na lista de campos:

```python
            Card.objects.bulk_update(
                cards_to_update,
                [
                    "color_identity",
                    "mana_value",
                    "is_commander_eligible",
                    "is_partner_eligible",
                    "scryfall_id",
                ],
                batch_size=2000,
            )
```

Note que `image_url` **não** entra nesse `bulk_update` — ele é responsabilidade da Task 4 (cache sob demanda), reimportar o MTGJSON não deve apagar imagens já resolvidas.

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import ast
tree = ast.parse(open('apps/core/management/commands/import_mtgjson.py').read())
print('sintaxe ok')
"
grep -n "scryfall_id" apps/core/management/commands/import_mtgjson.py
```

Esperado: "sintaxe ok" impresso, e o grep mostra as 4 ocorrências (extração, atributo no update, kwarg no create, entrada no bulk_update). Não rode o comando de verdade aqui — ele baixa ~30MB da internet e reescreve toda a tabela `Card`; isso é validado de fato quando alguém rodar `manage.py import_mtgjson` manualmente.

- [ ] **Step 3: Commit**

```bash
git add apps/core/management/commands/import_mtgjson.py
git commit -m "Capture scryfall_id when importing cards from MTGJSON"
```

### Task 4: `EnsureCardImageUseCase`

**Files:**
- Create: `apps/core/use_cases/card_image.py`
- Modify: `apps/core/use_cases/__init__.py`

**Interfaces:**
- Consumes: `apps.shared.use_cases.BaseUseCase`, `Card.scryfall_id`/`Card.image_url` (Task 2)
- Produces: `EnsureCardImageUseCase` — `.execute(card)` retorna `str` (URL da imagem) ou `None`. Usado pelas Tasks 14, 16 e 20 (dashboard, perfil do jogador, detalhe da partida).

- [ ] **Step 1: Implementar**

Criar `apps/core/use_cases/card_image.py`:

```python
import json
import logging
import urllib.error
import urllib.request

from apps.shared.use_cases import BaseUseCase

logger = logging.getLogger(__name__)

SCRYFALL_CARD_URL = "https://api.scryfall.com/cards/{scryfall_id}"


class EnsureCardImageUseCase(BaseUseCase):
    """
    Garante que um Card tenha `image_url` preenchido, buscando na API do
    Scryfall sob demanda e cacheando o resultado no próprio registro.
    Nunca derruba a tela que a chamou: falha de rede, carta sem
    scryfall_id, ou carta sem imagem simplesmente retornam None.
    """

    def perform_request(self, card):
        if card.image_url:
            return card.image_url

        if not card.scryfall_id:
            return None

        url = SCRYFALL_CARD_URL.format(scryfall_id=card.scryfall_id)
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, ValueError):
            logger.warning(
                "Não foi possível buscar imagem no Scryfall para %s", card.name
            )
            return None

        image_uris = payload.get("image_uris")
        if not image_uris and payload.get("card_faces"):
            image_uris = payload["card_faces"][0].get("image_uris")

        if not image_uris:
            return None

        image_url = image_uris.get("normal")
        if image_url:
            card.image_url = image_url
            card.save(update_fields=["image_url"])

        return image_url
```

Atualizar `apps/core/use_cases/__init__.py`:

```python
from .dashboard_stats import DashboardStatsUseCase
from .card_image import EnsureCardImageUseCase

__all__ = ["DashboardStatsUseCase", "EnsureCardImageUseCase"]
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from apps.core.models import Card
from apps.core.use_cases import EnsureCardImageUseCase

card = Card(name='Carta Sem Scryfall Id')
print('sem scryfall_id ->', EnsureCardImageUseCase().execute(card))

card2 = Card(name='Carta Com URL Em Cache', image_url='https://exemplo.com/ja-tenho.jpg')
print('ja tem image_url ->', EnsureCardImageUseCase().execute(card2))
"
```

Esperado: `sem scryfall_id -> None` e `ja tem image_url -> https://exemplo.com/ja-tenho.jpg` (nenhuma chamada de rede acontece em nenhum dos dois casos, os logs `[EnsureCardImageUseCase] iniciando/executado com sucesso/finalizado` aparecem no console pros dois).

- [ ] **Step 3: Commit**

```bash
git add apps/core/use_cases/card_image.py apps/core/use_cases/__init__.py
git commit -m "Add EnsureCardImageUseCase for on-demand Scryfall image caching"
```

---

## Parte C — Novas Métricas de Partida

### Task 5: Campos novos em `Game` e `GameParticipant` + migração

**Files:**
- Modify: `apps/core/models/game.py`
- Modify: `apps/core/models/game_participant.py`
- Create: `apps/core/migrations/0005_*.py` (nome exato gerado pelo Django)

**Interfaces:**
- Produces: `Game.turn_count` (int opcional); `GameParticipant.peak_life_total` (int opcional), `.board_wipes_count`/`.counterspell_count`/`.complaint_count` (int, default 0), `.is_self_elimination` (bool, default False), `.biggest_creature` (FK Card opcional), `.biggest_creature_power` (int opcional). Consumidos pelas Tasks 6, 7, 9, 15, 19.

- [ ] **Step 1: Implementar**

Em `apps/core/models/game.py`, adicionar `turn_count` entre `notes` e `created_at`:

```python
class Game(models.Model):
    date = models.DateField(
        null=True, blank=True, help_text="Data em que a partida foi realizada"
    )
    win_condition = models.CharField(
        max_length=30,
        choices=WinConditionChoices.choices,
        blank=True,
        help_text="Forma como o vencedor ganhou o jogo",
    )
    notes = models.TextField(
        blank=True, help_text="Observações ou momentos marcantes da partida"
    )
    turn_count = models.PositiveIntegerField(
        null=True, blank=True, help_text="Número de turnos até o fim da partida"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        date_str = self.date.strftime("%d/%m/%Y") if self.date else "Sem data"
        return f"Jogo #{self.pk} ({date_str})"
```

Reescrever `apps/core/models/game_participant.py` inteiro, adicionando os 6 campos entre `mvp_card` e `created_at`:

```python
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
from apps.core.models import Game, GameParticipant
game_fields = [f.name for f in Game._meta.get_fields()]
gp_fields = [f.name for f in GameParticipant._meta.get_fields()]
assert 'turn_count' in game_fields
for f in ['peak_life_total', 'board_wipes_count', 'counterspell_count', 'complaint_count', 'is_self_elimination', 'biggest_creature', 'biggest_creature_power']:
    assert f in gp_fields, f
print('todos os campos presentes')
"
```

Esperado: `migrate` roda sem erro, script imprime `todos os campos presentes`.

- [ ] **Step 3: Commit**

```bash
git add apps/core/models/game.py apps/core/models/game_participant.py apps/core/migrations/
git commit -m "Add turn_count and per-participant match metric fields"
```

### Task 6: Expor os campos novos no admin

**Files:**
- Modify: `apps/core/admin.py`

**Interfaces:**
- Consumes: campos novos da Task 5.

- [ ] **Step 1: Implementar**

Em `apps/core/admin.py`, atualizar `GameParticipantInline` (fields e autocomplete) e `formfield_for_foreignkey`:

```python
class GameParticipantInline(admin.TabularInline):
    model = GameParticipant
    extra = 4
    autocomplete_fields = ["player", "mvp_card", "biggest_creature"]
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
    )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        formfield = super().formfield_for_foreignkey(db_field, request, **kwargs)
        if db_field.name in ("mvp_card", "biggest_creature"):
            formfield.widget.can_add_related = False
        return formfield
```

E em `GameAdmin`, adicionar `turn_count` ao `list_display`:

```python
@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = (
        "get_game_title",
        "date",
        "win_condition",
        "turn_count",
        "get_winner",
        "created_at",
    )
```

(o resto de `GameAdmin` não muda)

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python manage.py check
```

Esperado: `System check identified no issues (0 silenced).` — o Django valida automaticamente que todo campo listado em `fields`/`list_display`/`autocomplete_fields` existe no model; qualquer erro de digitação nos nomes dos campos apareceria aqui.

- [ ] **Step 3: Commit**

```bash
git add apps/core/admin.py
git commit -m "Surface new match metric fields in Django admin"
```

### Task 7: `seed_games.py` popula os campos novos

**Files:**
- Modify: `apps/core/management/commands/seed_games.py`

**Interfaces:**
- Consumes: campos novos da Task 5.

- [ ] **Step 1: Implementar**

Adicionar `turn_count` na criação do `Game`:

```python
            game = Game.objects.create(
                date=game_date,
                win_condition=random.choice(WIN_CONDITIONS),
                notes="Partida gerada via CLI.",
                turn_count=random.randint(4, 14),
            )
```

E, dentro do loop de participantes, calcular e passar os campos novos na criação do `GameParticipant`:

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
                )
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python manage.py seed_games --total 5
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from apps.core.models import GameParticipant, Game
gp = GameParticipant.objects.first()
print('turn_count em algum Game:', Game.objects.exclude(turn_count__isnull=True).exists())
print('board_wipes_count é int:', isinstance(gp.board_wipes_count, int))
print('is_self_elimination é bool:', isinstance(gp.is_self_elimination, bool))
"
```

Esperado: `seed_games` roda sem erro (usa `DEBUG=True` de `config.settings.local`), e o script confirma `True` nas três checagens.

- [ ] **Step 3: Commit**

```bash
git add apps/core/management/commands/seed_games.py
git commit -m "Seed new match metric fields with realistic random dev data"
```

---

## Parte D — Dashboard Enriquecido (`PodInsightsUseCase`)

### Task 8: `PodInsightsUseCase` — cores, tendência, pontuação, top qualificado e recordes

**Files:**
- Create: `apps/core/use_cases/pod_insights.py`
- Modify: `apps/core/use_cases/__init__.py`

**Interfaces:**
- Consumes: `Deck.color_identity`, `Game.date`/`.win_condition`/`.turn_count`, `GameParticipant` (todos os campos, incluindo os novos da Task 5).
- Produces: `PodInsightsUseCase` — `.execute()` retorna um dict com as chaves `color_identity_stats`, `color_count_stats`, `wincon_trend`, `points_ranking`, `top_commanders_qualified`, `records`. Também expõe o módulo-level `POINTS_BY_PLACEMENT = {1: 4, 2: 2, 3: 1}`, reutilizado pela Task 15 (`PlayerProfileUseCase`).

- [ ] **Step 1: Implementar**

Criar `apps/core/use_cases/pod_insights.py`:

```python
from django.db.models import Count, Q
from django.db.models.functions import TruncMonth

from apps.core.models import Deck, Game, GameParticipant, Player
from apps.shared.use_cases import BaseUseCase

POINTS_BY_PLACEMENT = {1: 4, 2: 2, 3: 1}


class PodInsightsUseCase(BaseUseCase):
    def perform_request(self) -> dict:
        return {
            "color_identity_stats": self._color_identity_stats(),
            "color_count_stats": self._color_count_stats(),
            "wincon_trend": self._wincon_trend(),
            "points_ranking": self._points_ranking(),
            "top_commanders_qualified": self._top_commanders_qualified(),
            "records": self._records(),
        }

    def _color_identity_stats(self):
        stats = []
        for color in "WUBRG":
            decks_with_color = Deck.objects.filter(color_identity__contains=color)
            performances = GameParticipant.objects.filter(deck__in=decks_with_color)
            games = performances.count()
            wins = performances.filter(placement=1).count()
            win_rate = round((wins / games * 100), 1) if games else 0
            stats.append(
                {"color": color, "games": games, "wins": wins, "win_rate": win_rate}
            )
        return stats

    def _color_count_stats(self):
        decks = Deck.objects.annotate(
            games=Count("match_performances"),
            wins=Count(
                "match_performances", filter=Q(match_performances__placement=1)
            ),
        )
        buckets = {n: {"games": 0, "wins": 0} for n in range(6)}
        for deck in decks:
            num_colors = (
                0 if deck.color_identity in ("", "C") else len(deck.color_identity)
            )
            buckets[num_colors]["games"] += deck.games
            buckets[num_colors]["wins"] += deck.wins

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

    def _wincon_trend(self):
        trend = (
            Game.objects.exclude(date__isnull=True)
            .annotate(month=TruncMonth("date"))
            .values("month", "win_condition")
            .annotate(count=Count("id"))
            .order_by("month", "win_condition")
        )
        return list(trend)

    def _points_ranking(self):
        ranking = []
        for player in Player.objects.all():
            performances = player.match_performances.all()
            points = sum(
                POINTS_BY_PLACEMENT.get(p.placement, 0) for p in performances
            )
            ranking.append({"player": player, "points": points})
        ranking.sort(key=lambda row: row["points"], reverse=True)
        return ranking

    def _top_commanders_qualified(self):
        decks = Deck.objects.annotate(
            games=Count("match_performances"),
            wins=Count(
                "match_performances", filter=Q(match_performances__placement=1)
            ),
        ).filter(games__gte=5)

        qualified = []
        for deck in decks:
            win_rate = round((deck.wins / deck.games * 100), 1) if deck.games else 0
            if win_rate >= 20:
                qualified.append(
                    {
                        "deck": deck,
                        "games": deck.games,
                        "wins": deck.wins,
                        "win_rate": win_rate,
                    }
                )
        qualified.sort(key=lambda row: row["win_rate"], reverse=True)
        return qualified

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
        }
```

Atualizar `apps/core/use_cases/__init__.py`:

```python
from .dashboard_stats import DashboardStatsUseCase
from .pod_insights import PodInsightsUseCase
from .card_image import EnsureCardImageUseCase

__all__ = ["DashboardStatsUseCase", "PodInsightsUseCase", "EnsureCardImageUseCase"]
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from apps.core.use_cases import PodInsightsUseCase
data = PodInsightsUseCase().execute()
print(sorted(data.keys()))
print('cores:', [row['color'] for row in data['color_identity_stats']])
print('records keys:', sorted(data['records'].keys()))
"
```

Esperado: a lista de chaves impressa é
`['color_count_stats', 'color_identity_stats', 'points_ranking', 'records', 'top_commanders_qualified', 'wincon_trend']`,
`cores: ['W', 'U', 'B', 'R', 'G']`, e as chaves de `records` batem com as 8 definidas em `_records()`.

- [ ] **Step 3: Commit**

```bash
git add apps/core/use_cases/pod_insights.py apps/core/use_cases/__init__.py
git commit -m "Add PodInsightsUseCase for color/points/trend stats and global records"
```

### Task 9: Ligar `PodInsightsUseCase` + imagem do MVP ao `DashboardView`

**Files:**
- Modify: `apps/core/use_cases/dashboard_stats.py`
- Modify: `apps/core/views/dashboard.py`

**Interfaces:**
- Consumes: `PodInsightsUseCase` (Task 8), `EnsureCardImageUseCase` (Task 4).
- Produces: `context["top_player"]`/`context["ranked_players"]` passam a ter a chave `"id"`; `context["top_mvp"]` passa a ter as chaves `"id"` e `"image_url"`. Consumido pela Task 10 (template) e reaproveitado pela Task 16 (link do jogador no template de perfil não depende disso, mas o dashboard sim).

- [ ] **Step 1: Implementar**

Em `apps/core/use_cases/dashboard_stats.py`, adicionar `"id": player.id` na construção de `ranked_players`, e trocar a query de `top_mvp` pra trazer o id da carta:

```python
        ranked_players = []
        for player in players:
            wr = (
                round((player.wins / player.total_games * 100), 1)
                if player.total_games > 0
                else 0
            )
            ranked_players.append(
                {
                    "id": player.id,
                    "name": player.name,
                    "wins": player.wins,
                    "total_games": player.total_games,
                    "win_rate": wr,
                }
            )
```

```python
        # Carta MVP
        top_mvp_query = (
            GameParticipant.objects.filter(mvp_card__isnull=False)
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
```

(o resto do arquivo não muda)

Reescrever `apps/core/views/dashboard.py`:

```python
from django.views.generic import TemplateView
from apps.core.models import Card
from apps.core.use_cases import (
    DashboardStatsUseCase,
    EnsureCardImageUseCase,
    PodInsightsUseCase,
)


class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(DashboardStatsUseCase().execute())
        context.update(PodInsightsUseCase().execute())

        top_mvp = context.get("top_mvp")
        if top_mvp:
            card = Card.objects.filter(pk=top_mvp["id"]).first()
            top_mvp["image_url"] = (
                EnsureCardImageUseCase().execute(card) if card else None
            )

        return context
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
print('top_player tem id:', 'id' in (resp.context['top_player'] or {}))
print('pod insights presente:', 'color_identity_stats' in resp.context)
"
```

Esperado: `status: 200`, `top_player tem id: True` (ou `False` só se não houver nenhum jogador cadastrado), `pod insights presente: True`.

- [ ] **Step 3: Commit**

```bash
git add apps/core/use_cases/dashboard_stats.py apps/core/views/dashboard.py
git commit -m "Wire PodInsightsUseCase and MVP card image into DashboardView"
```

### Task 10: Template do dashboard — links de jogador, imagem do MVP, novas seções

**Files:**
- Modify: `apps/core/templates/core/dashboard.html`

**Interfaces:**
- Consumes: contexto produzido pela Task 9 (`top_player`/`ranked_players` com `id`, `top_mvp` com `image_url`) e pela Task 8 (`color_identity_stats`, `color_count_stats`, `wincon_trend`, `points_ranking`, `top_commanders_qualified`, `records`). Depende da rota `core:player-profile` e `core:game-detail`, criadas na Task 16.

> Esta tarefa só faz sentido rodar (o servidor não vai quebrar antes disso,
> mas os links de jogador/partida ficam quebrados) depois da Task 16
> existir. Ainda assim, implemente aqui — a Task 16 não depende do
> template, só o contrário.

- [ ] **Step 1: Implementar**

No card "Maior Vencedor" (topo), tornar o nome um link:

```html
    <div class="p-4 bg-amber-50/40 border border-amber-200/80 rounded-xl">
      <span class="text-[11px] font-bold text-amber-700 tracking-wider uppercase flex items-center gap-1">
        🏆 MAIOR VENCEDOR
      </span>
      <p class="text-2xl font-bold text-gray-900 mt-2">
        {% if top_player %}<a href="{% url 'core:player-profile' top_player.id %}" class="hover:underline">{{ top_player.name }}</a>{% else %}-{% endif %}
      </p>
      <p class="text-xs text-amber-700 font-medium mt-1">
        {{ top_player.wins|default:0 }} vitórias ({{ top_player.win_rate|default:0 }}% winrate)
      </p>
    </div>
```

No card "Carta MVP", mostrar a imagem quando existir:

```html
    <div class="p-4 bg-white border border-gray-200 rounded-xl flex items-center gap-3">
      {% if top_mvp.image_url %}
      <img src="{{ top_mvp.image_url }}" alt="{{ top_mvp.name }}" class="w-12 h-auto rounded-md border border-gray-200" />
      {% endif %}
      <div class="min-w-0">
        <span class="text-[11px] font-bold text-amber-600 tracking-wider uppercase flex items-center gap-1">
          🌟 CARTA MVP
        </span>
        <p class="text-xl font-bold text-gray-900 mt-2 truncate">
          {{ top_mvp.name|default:"-" }}
        </p>
        <p class="text-xs text-gray-400 mt-1">Mais votada como destaque</p>
      </div>
    </div>
```

Na tabela de Achievements, tornar o nome do jogador um link (`achievement.player` já é um objeto `Player` via `select_related`):

```html
                <td class="p-4 font-medium text-gray-900">
                  {% if achievement.player %}
                  <a href="{% url 'core:player-profile' achievement.player.id %}" class="hover:underline">{{ achievement.player.name }}</a>
                  {% else %}-{% endif %}
                </td>
```

No ranking da coluna direita, tornar o nome um link:

```html
              <div>
                <p class="text-sm font-bold text-gray-900">
                  <a href="{% url 'core:player-profile' player.id %}" class="hover:underline">{{ player.name }}</a>
                </p>
                <p class="text-xs text-gray-400">{{ player.total_games }} partidas ({{ player.win_rate }}% WR)</p>
              </div>
```

Por fim, antes do `{% endblock %}` final, adicionar as seções novas (pontuação, cores, top qualificado, tendência de wincon, e recordes):

```html
  <!-- Pontuação estilo F1 -->
  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="p-4 border-b border-gray-100 bg-gray-50/50">
      <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">PONTUAÇÃO (4-2-1-0)</h2>
    </div>
    <div class="divide-y divide-gray-100">
      {% for row in points_ranking %}
      <div class="p-4 flex items-center justify-between text-sm">
        <a href="{% url 'core:player-profile' row.player.id %}" class="font-medium text-gray-700 hover:underline">{{ row.player.name }}</a>
        <span class="font-bold text-gray-900">{{ row.points }} pts</span>
      </div>
      {% empty %}
      <div class="p-4 text-center text-xs text-gray-400">Nenhuma partida registrada.</div>
      {% endfor %}
    </div>
  </div>

  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <!-- Win rate por cor -->
    <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      <div class="p-4 border-b border-gray-100 bg-gray-50/50">
        <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">WIN RATE POR COR</h2>
      </div>
      <div class="divide-y divide-gray-100">
        {% for row in color_identity_stats %}
        <div class="p-4 flex items-center justify-between text-sm">
          <span class="font-medium text-gray-700">{{ row.color }}</span>
          <span class="text-gray-500">{{ row.games }} jogos</span>
          <span class="font-bold text-gray-900">{{ row.win_rate }}%</span>
        </div>
        {% endfor %}
      </div>
    </div>

    <!-- Win rate por número de cores -->
    <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
      <div class="p-4 border-b border-gray-100 bg-gray-50/50">
        <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">WIN RATE POR Nº DE CORES</h2>
      </div>
      <div class="divide-y divide-gray-100">
        {% for row in color_count_stats %}
        <div class="p-4 flex items-center justify-between text-sm">
          <span class="font-medium text-gray-700">{{ row.colors }} cor(es)</span>
          <span class="text-gray-500">{{ row.games }} jogos</span>
          <span class="font-bold text-gray-900">{{ row.win_rate }}%</span>
        </div>
        {% endfor %}
      </div>
    </div>
  </div>

  <!-- Top comandantes qualificados -->
  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="p-4 border-b border-gray-100 bg-gray-50/50">
      <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">TOP COMANDANTES (≥5 jogos, ≥20% WR)</h2>
    </div>
    <div class="divide-y divide-gray-100">
      {% for row in top_commanders_qualified %}
      <div class="p-4 flex items-center justify-between text-sm">
        <span class="font-medium text-gray-700">{{ row.deck.display_commanders }}</span>
        <span class="text-gray-500">{{ row.games }} jogos</span>
        <span class="font-bold text-gray-900">{{ row.win_rate }}%</span>
      </div>
      {% empty %}
      <div class="p-4 text-center text-xs text-gray-400">Nenhum comandante qualificado ainda.</div>
      {% endfor %}
    </div>
  </div>

  <!-- Wincon por mês -->
  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="p-4 border-b border-gray-100 bg-gray-50/50">
      <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">WINCON POR MÊS</h2>
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-sm">
        <thead>
          <tr class="bg-gray-50/30 border-b border-gray-100 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
            <th class="p-4">Mês</th>
            <th class="p-4">Wincon</th>
            <th class="p-4">Jogos</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          {% for row in wincon_trend %}
          <tr>
            <td class="p-4">{{ row.month|date:"M/Y" }}</td>
            <td class="p-4 capitalize">{{ row.win_condition }}</td>
            <td class="p-4 font-semibold">{{ row.count }}</td>
          </tr>
          {% empty %}
          <tr><td colspan="3" class="p-6 text-center text-xs text-gray-400">Sem dados suficientes.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Recordes do Pod -->
  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="p-4 border-b border-gray-100 bg-gray-50/50">
      <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">RECORDES DO POD</h2>
    </div>
    <div class="divide-y divide-gray-100 text-sm">
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Maior board wipe (numa partida)</span>
        {% if records.board_wipes %}
        <a href="{% url 'core:game-detail' records.board_wipes.game.id %}" class="font-semibold text-gray-900 hover:underline">
          {{ records.board_wipes.player.name }} ({{ records.board_wipes.board_wipes_count }})
        </a>
        {% else %}<span class="text-gray-400">-</span>{% endif %}
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Mais counterspells (numa partida)</span>
        {% if records.counterspells %}
        <a href="{% url 'core:game-detail' records.counterspells.game.id %}" class="font-semibold text-gray-900 hover:underline">
          {{ records.counterspells.player.name }} ({{ records.counterspells.counterspell_count }})
        </a>
        {% else %}<span class="text-gray-400">-</span>{% endif %}
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Maior chorão (numa partida)</span>
        {% if records.complaints %}
        <a href="{% url 'core:game-detail' records.complaints.game.id %}" class="font-semibold text-gray-900 hover:underline">
          {{ records.complaints.player.name }} ({{ records.complaints.complaint_count }})
        </a>
        {% else %}<span class="text-gray-400">-</span>{% endif %}
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Mais vida numa partida</span>
        {% if records.most_life %}
        <a href="{% url 'core:game-detail' records.most_life.game.id %}" class="font-semibold text-gray-900 hover:underline">
          {{ records.most_life.player.name }} ({{ records.most_life.peak_life_total }})
        </a>
        {% else %}<span class="text-gray-400">-</span>{% endif %}
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Maior criatura (poder alcançado)</span>
        {% if records.biggest_creature %}
        <a href="{% url 'core:game-detail' records.biggest_creature.game.id %}" class="font-semibold text-gray-900 hover:underline">
          {{ records.biggest_creature.biggest_creature.name }} ({{ records.biggest_creature.biggest_creature_power }})
        </a>
        {% else %}<span class="text-gray-400">-</span>{% endif %}
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Suicídios registrados</span>
        <span class="font-semibold text-gray-900">{{ records.self_eliminations_count }}</span>
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Jogo mais rápido (sem combo)</span>
        {% if records.fastest_game_no_combo %}
        <a href="{% url 'core:game-detail' records.fastest_game_no_combo.id %}" class="font-semibold text-gray-900 hover:underline">
          {{ records.fastest_game_no_combo.turn_count }} turnos
        </a>
        {% else %}<span class="text-gray-400">-</span>{% endif %}
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Jogo mais rápido (com combo)</span>
        {% if records.fastest_game_combo %}
        <a href="{% url 'core:game-detail' records.fastest_game_combo.id %}" class="font-semibold text-gray-900 hover:underline">
          {{ records.fastest_game_combo.turn_count }} turnos
        </a>
        {% else %}<span class="text-gray-400">-</span>{% endif %}
      </div>
    </div>
  </div>
```

- [ ] **Step 2: Verificar**

Rode a verificação da Task 9 de novo (o `Client().get('/')` renderiza o template inteiro, então qualquer `{% url %}` quebrado ou erro de sintaxe do template aparece como uma exceção nesse momento):

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

Esperado: `status: 200` — se as rotas `core:player-profile`/`core:game-detail` ainda não existirem (Task 16), isso vai falhar com `NoReverseMatch`; nesse caso, pule a verificação desta task e volte a ela depois de completar a Parte E e F.

- [ ] **Step 3: Commit**

```bash
git add apps/core/templates/core/dashboard.html
git commit -m "Enrich dashboard template with player links, MVP image, and pod insights"
```

---

## Parte E — Perfil do Jogador

### Task 11: `PlayerProfileUseCase`

**Files:**
- Create: `apps/core/use_cases/player_profile.py`
- Modify: `apps/core/use_cases/__init__.py`

**Interfaces:**
- Consumes: `POINTS_BY_PLACEMENT` (Task 8, `pod_insights.py`), campos novos de `GameParticipant` (Task 5).
- Produces: `PlayerProfileUseCase` — `.execute(player)` retorna dict com `total_games`, `wins`, `win_rate`, `points`, `commander_stats` (lista de `{deck, games, wins, win_rate}`), `records` (dict com `board_wipes`, `counterspells`, `complaints`, `most_life`, `biggest_creature`). Consumido pela Task 13.

- [ ] **Step 1: Implementar**

Criar `apps/core/use_cases/player_profile.py`:

```python
from django.db.models import Count, Q

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
        }
```

Atualizar `apps/core/use_cases/__init__.py`:

```python
from .dashboard_stats import DashboardStatsUseCase
from .pod_insights import PodInsightsUseCase
from .player_profile import PlayerProfileUseCase
from .card_image import EnsureCardImageUseCase

__all__ = [
    "DashboardStatsUseCase",
    "PodInsightsUseCase",
    "PlayerProfileUseCase",
    "EnsureCardImageUseCase",
]
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
print(sorted(data.keys()))
print('total_games:', data['total_games'])
"
```

Esperado: chaves impressas =
`['commander_stats', 'points', 'records', 'total_games', 'win_rate', 'wins']`,
e `total_games` é um inteiro ≥ 0. Se não houver nenhum `Player` no banco (rode `seed_games` antes se precisar), o script vai falhar com `AttributeError` em `player.match_performances` — nesse caso rode `manage.py seed_games --total 5` primeiro.

- [ ] **Step 3: Commit**

```bash
git add apps/core/use_cases/player_profile.py apps/core/use_cases/__init__.py
git commit -m "Add PlayerProfileUseCase for per-player stats and personal records"
```

### Task 12: `PlayerProfileView` + rota

**Files:**
- Create: `apps/core/views/player_profile.py`
- Modify: `apps/core/views/__init__.py`
- Modify: `apps/core/urls.py`

**Interfaces:**
- Consumes: `PlayerProfileUseCase` (Task 11).
- Produces: rota nomeada `core:player-profile`, aceitando `<int:pk>`. Consumida pelos templates da Task 10 e Task 13.

- [ ] **Step 1: Implementar**

Criar `apps/core/views/player_profile.py`:

```python
from django.views.generic import DetailView
from apps.core.models import Player
from apps.core.use_cases import PlayerProfileUseCase


class PlayerProfileView(DetailView):
    model = Player
    template_name = "core/player_profile.html"
    context_object_name = "player"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(PlayerProfileUseCase().execute(self.object))
        return context
```

Atualizar `apps/core/views/__init__.py`:

```python
from .dashboard import DashboardView
from .player_profile import PlayerProfileView

__all__ = ["DashboardView", "PlayerProfileView"]
```

Atualizar `apps/core/urls.py`:

```python
from django.urls import path
from apps.core.views import DashboardView, PlayerProfileView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("players/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
]
```

- [ ] **Step 2: Verificar**

```bash
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

Esperado: essa verificação só passa depois que `player_profile.html` existir (Task 13) — até lá, espere um `TemplateDoesNotExist`. Rode `manage.py check` agora pra confirmar que a view e a URL em si estão corretas:

```bash
.venv/bin/python manage.py check
```

Esperado: `System check identified no issues (0 silenced).`

- [ ] **Step 3: Commit**

```bash
git add apps/core/views/player_profile.py apps/core/views/__init__.py apps/core/urls.py
git commit -m "Add PlayerProfileView and /players/<id>/ route"
```

### Task 13: Template `player_profile.html`

**Files:**
- Create: `apps/core/templates/core/player_profile.html`

**Interfaces:**
- Consumes: contexto da Task 11/12.

- [ ] **Step 1: Implementar**

Criar `apps/core/templates/core/player_profile.html`:

```html
{% extends "base.html" %}

{% block content %}
<div class="space-y-6">

  <div>
    <h1 class="text-2xl font-bold text-gray-900">{{ player.name }}</h1>
    <p class="text-sm text-gray-500">Perfil do jogador</p>
  </div>

  <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
    <div class="p-4 bg-white border border-gray-200 rounded-xl">
      <span class="text-[10px] font-bold text-gray-400 tracking-wider uppercase">PARTIDAS</span>
      <p class="text-2xl font-bold text-gray-900 mt-1">{{ total_games }}</p>
    </div>
    <div class="p-4 bg-white border border-gray-200 rounded-xl">
      <span class="text-[10px] font-bold text-gray-400 tracking-wider uppercase">VITÓRIAS</span>
      <p class="text-2xl font-bold text-gray-900 mt-1">{{ wins }}</p>
    </div>
    <div class="p-4 bg-white border border-gray-200 rounded-xl">
      <span class="text-[10px] font-bold text-gray-400 tracking-wider uppercase">WIN RATE</span>
      <p class="text-2xl font-bold text-gray-900 mt-1">{{ win_rate }}%</p>
    </div>
    <div class="p-4 bg-white border border-gray-200 rounded-xl">
      <span class="text-[10px] font-bold text-gray-400 tracking-wider uppercase">PONTOS (4-2-1-0)</span>
      <p class="text-2xl font-bold text-gray-900 mt-1">{{ points }}</p>
    </div>
  </div>

  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="p-4 border-b border-gray-100 bg-gray-50/50">
      <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">COMANDANTES PILOTADOS</h2>
    </div>
    <div class="divide-y divide-gray-100">
      {% for row in commander_stats %}
      <div class="p-4 flex items-center justify-between text-sm">
        <span class="font-medium text-gray-700">{{ row.deck.display_commanders|default:"Sem comandante" }}</span>
        <span class="text-gray-500">{{ row.games }} jogos</span>
        <span class="font-bold text-gray-900">{{ row.wins }} vitórias ({{ row.win_rate }}%)</span>
      </div>
      {% empty %}
      <div class="p-4 text-center text-xs text-gray-400">Nenhum deck cadastrado ainda.</div>
      {% endfor %}
    </div>
  </div>

  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="p-4 border-b border-gray-100 bg-gray-50/50">
      <h2 class="text-xs font-bold text-gray-900 uppercase tracking-wider">RECORDES PESSOAIS</h2>
    </div>
    <div class="divide-y divide-gray-100 text-sm">
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Board wipes numa partida</span>
        <span class="font-semibold text-gray-900">
          {% if records.board_wipes %}{{ records.board_wipes.board_wipes_count }}{% else %}-{% endif %}
        </span>
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Counterspells numa partida</span>
        <span class="font-semibold text-gray-900">
          {% if records.counterspells %}{{ records.counterspells.counterspell_count }}{% else %}-{% endif %}
        </span>
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Reclamações numa partida</span>
        <span class="font-semibold text-gray-900">
          {% if records.complaints %}{{ records.complaints.complaint_count }}{% else %}-{% endif %}
        </span>
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Vida de pico numa partida</span>
        <span class="font-semibold text-gray-900">
          {% if records.most_life %}{{ records.most_life.peak_life_total }}{% else %}-{% endif %}
        </span>
      </div>
      <div class="p-4 flex items-center justify-between">
        <span class="text-gray-500">Maior criatura (poder alcançado)</span>
        <span class="font-semibold text-gray-900">
          {% if records.biggest_creature %}{{ records.biggest_creature.biggest_creature.name }} ({{ records.biggest_creature.biggest_creature_power }}){% else %}-{% endif %}
        </span>
      </div>
    </div>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 2: Verificar**

```bash
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

Esperado: `status: 200`.

- [ ] **Step 3: Commit**

```bash
git add apps/core/templates/core/player_profile.html
git commit -m "Add player profile template"
```

---

## Parte F — Lista e Detalhe de Partidas

### Task 14: `GameDetailUseCase`

**Files:**
- Create: `apps/core/use_cases/game_detail.py`
- Modify: `apps/core/use_cases/__init__.py`

**Interfaces:**
- Consumes: `Game`, `GameParticipant` (com `select_related`/`prefetch_related`).
- Produces: `GameDetailUseCase` — `.execute(game)` retorna `{"participants": [...]}`, uma lista de `GameParticipant` ordenada por `placement`, com `player`/`deck`/`mvp_card` pré-carregados e `deck.commanders` pré-carregado. Consumido pela Task 16.

- [ ] **Step 1: Implementar**

Criar `apps/core/use_cases/game_detail.py`:

```python
from apps.core.models import Game
from apps.shared.use_cases import BaseUseCase


class GameDetailUseCase(BaseUseCase):
    def perform_request(self, game: Game) -> dict:
        participants = (
            game.participants.select_related("player", "deck", "mvp_card")
            .prefetch_related("deck__commanders")
            .order_by("placement")
        )
        return {"participants": list(participants)}
```

Atualizar `apps/core/use_cases/__init__.py`:

```python
from .dashboard_stats import DashboardStatsUseCase
from .pod_insights import PodInsightsUseCase
from .player_profile import PlayerProfileUseCase
from .game_detail import GameDetailUseCase
from .card_image import EnsureCardImageUseCase

__all__ = [
    "DashboardStatsUseCase",
    "PodInsightsUseCase",
    "PlayerProfileUseCase",
    "GameDetailUseCase",
    "EnsureCardImageUseCase",
]
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from apps.core.models import Game
from apps.core.use_cases import GameDetailUseCase
game = Game.objects.first()
data = GameDetailUseCase().execute(game)
print(sorted(data.keys()))
print('participantes:', len(data['participants']))
"
```

Esperado: `['participants']` e um número de participantes ≥ 0. Se não houver nenhum `Game`, rode `manage.py seed_games --total 5` primeiro.

- [ ] **Step 3: Commit**

```bash
git add apps/core/use_cases/game_detail.py apps/core/use_cases/__init__.py
git commit -m "Add GameDetailUseCase"
```

### Task 15: `GameListView` + `GameDetailView` + rotas

**Files:**
- Create: `apps/core/views/game_list.py`
- Create: `apps/core/views/game_detail.py`
- Modify: `apps/core/views/__init__.py`
- Modify: `apps/core/urls.py`

**Interfaces:**
- Consumes: `GameDetailUseCase` (Task 14), `EnsureCardImageUseCase` (Task 4).
- Produces: rotas `core:game-list` (`/games/`) e `core:game-detail` (`/games/<int:pk>/`). `GameDetailView` monta `context["rows"]`, uma lista de `{"participant": GameParticipant, "commander_images": [(Card, url_ou_None), ...], "mvp_image_url": url_ou_None}` — consumida pela Task 16.

- [ ] **Step 1: Implementar**

`GameListView` não precisa de use case — é uma listagem paginada simples, sem regra de negócio, o padrão idiomático do Django (`ListView.get_queryset`) já resolve isso sem indireção extra. Criar `apps/core/views/game_list.py`:

```python
from django.views.generic import ListView
from apps.core.models import Game


class GameListView(ListView):
    model = Game
    template_name = "core/game_list.html"
    context_object_name = "games"
    paginate_by = 20

    def get_queryset(self):
        return Game.objects.prefetch_related("participants__player").order_by(
            "-date", "-id"
        )
```

Criar `apps/core/views/game_detail.py`:

```python
from django.views.generic import DetailView
from apps.core.models import Game
from apps.core.use_cases import EnsureCardImageUseCase, GameDetailUseCase


class GameDetailView(DetailView):
    model = Game
    template_name = "core/game_detail.html"
    context_object_name = "game"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        data = GameDetailUseCase().execute(self.object)
        image_use_case = EnsureCardImageUseCase()

        rows = []
        for participant in data["participants"]:
            commander_images = (
                [
                    (card, image_use_case.execute(card))
                    for card in participant.deck.commanders.all()
                ]
                if participant.deck
                else []
            )
            mvp_image_url = (
                image_use_case.execute(participant.mvp_card)
                if participant.mvp_card
                else None
            )
            rows.append(
                {
                    "participant": participant,
                    "commander_images": commander_images,
                    "mvp_image_url": mvp_image_url,
                }
            )

        context["rows"] = rows
        return context
```

Atualizar `apps/core/views/__init__.py`:

```python
from .dashboard import DashboardView
from .player_profile import PlayerProfileView
from .game_list import GameListView
from .game_detail import GameDetailView

__all__ = ["DashboardView", "PlayerProfileView", "GameListView", "GameDetailView"]
```

Atualizar `apps/core/urls.py`:

```python
from django.urls import path
from apps.core.views import DashboardView, GameDetailView, GameListView, PlayerProfileView

urlpatterns = [
    path("", DashboardView.as_view(), name="dashboard"),
    path("players/<int:pk>/", PlayerProfileView.as_view(), name="player-profile"),
    path("games/", GameListView.as_view(), name="game-list"),
    path("games/<int:pk>/", GameDetailView.as_view(), name="game-detail"),
]
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python manage.py check
```

Esperado: `System check identified no issues (0 silenced).` (os templates ainda não existem, então acessar as rotas de verdade só funciona depois da Task 16 — `check` já confirma que views/rotas estão corretas).

- [ ] **Step 3: Commit**

```bash
git add apps/core/views/game_list.py apps/core/views/game_detail.py apps/core/views/__init__.py apps/core/urls.py
git commit -m "Add GameListView and GameDetailView with routes"
```

### Task 16: Templates `game_list.html` e `game_detail.html` + link "Partidas" na nav

**Files:**
- Create: `apps/core/templates/core/game_list.html`
- Create: `apps/core/templates/core/game_detail.html`
- Modify: `templates/base.html`

**Interfaces:**
- Consumes: contexto das Tasks 14/15.

- [ ] **Step 1: Implementar**

Criar `apps/core/templates/core/game_list.html`:

```html
{% extends "base.html" %}

{% block content %}
<div class="space-y-6">

  <div>
    <h1 class="text-2xl font-bold text-gray-900">Partidas</h1>
    <p class="text-sm text-gray-500">Histórico completo, mais recente primeiro.</p>
  </div>

  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-sm">
        <thead>
          <tr class="bg-gray-50/30 border-b border-gray-100 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
            <th class="p-4">Data</th>
            <th class="p-4">Wincon</th>
            <th class="p-4">Jogadores</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          {% for game in games %}
          <tr class="hover:bg-gray-50/50 transition">
            <td class="p-4">
              <a href="{% url 'core:game-detail' game.id %}" class="font-semibold text-gray-900 hover:underline">
                {{ game.date|date:"d/m/Y"|default:"Sem data" }}
              </a>
            </td>
            <td class="p-4 capitalize">{{ game.win_condition|default:"-" }}</td>
            <td class="p-4 text-gray-600">
              {% for participant in game.participants.all %}{{ participant.player.name }}{% if not forloop.last %}, {% endif %}{% endfor %}
            </td>
          </tr>
          {% empty %}
          <tr><td colspan="3" class="p-6 text-center text-xs text-gray-400">Nenhuma partida registrada.</td></tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

  {% if is_paginated %}
  <div class="flex justify-center gap-4 text-sm">
    {% if page_obj.has_previous %}
    <a href="?page={{ page_obj.previous_page_number }}" class="text-gray-600 hover:text-gray-900">« Anterior</a>
    {% endif %}
    <span class="text-gray-400">Página {{ page_obj.number }} de {{ page_obj.paginator.num_pages }}</span>
    {% if page_obj.has_next %}
    <a href="?page={{ page_obj.next_page_number }}" class="text-gray-600 hover:text-gray-900">Próxima »</a>
    {% endif %}
  </div>
  {% endif %}

</div>
{% endblock %}
```

Criar `apps/core/templates/core/game_detail.html`:

```html
{% extends "base.html" %}

{% block content %}
<div class="space-y-6">

  <div>
    <h1 class="text-2xl font-bold text-gray-900">Partida de {{ game.date|date:"d/m/Y"|default:"data desconhecida" }}</h1>
    <p class="text-sm text-gray-500">
      Wincon: <span class="capitalize">{{ game.win_condition|default:"-" }}</span>
      {% if game.turn_count %} • {{ game.turn_count }} turnos{% endif %}
    </p>
  </div>

  <div class="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
    <div class="overflow-x-auto">
      <table class="w-full text-left border-collapse text-sm">
        <thead>
          <tr class="bg-gray-50/30 border-b border-gray-100 text-[11px] font-bold text-gray-400 uppercase tracking-wider">
            <th class="p-4">Jogador</th>
            <th class="p-4">Comandante(s)</th>
            <th class="p-4">Colocação</th>
            <th class="p-4">Kills</th>
            <th class="p-4">Board Wipes</th>
            <th class="p-4">Counterspells</th>
            <th class="p-4">Reclamações</th>
            <th class="p-4">Vida de Pico</th>
            <th class="p-4">MVP</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-gray-100">
          {% for row in rows %}
          <tr class="hover:bg-gray-50/50 transition">
            <td class="p-4 font-semibold text-gray-900">
              <a href="{% url 'core:player-profile' row.participant.player.id %}" class="hover:underline">{{ row.participant.player.name }}</a>
              {% if row.participant.is_self_elimination %}<span class="ml-1 text-xs text-red-500">(suicídio)</span>{% endif %}
            </td>
            <td class="p-4">
              <div class="flex items-center gap-2">
                {% for card, image_url in row.commander_images %}
                {% if image_url %}<img src="{{ image_url }}" alt="{{ card.name }}" class="w-8 h-auto rounded" />{% endif %}
                <span class="text-gray-700">{{ card.name }}</span>
                {% endfor %}
              </div>
            </td>
            <td class="p-4">{{ row.participant.placement }}º</td>
            <td class="p-4">{{ row.participant.kill_count }}</td>
            <td class="p-4">{{ row.participant.board_wipes_count }}</td>
            <td class="p-4">{{ row.participant.counterspell_count }}</td>
            <td class="p-4">{{ row.participant.complaint_count }}</td>
            <td class="p-4">{{ row.participant.peak_life_total|default:"-" }}</td>
            <td class="p-4">
              {% if row.mvp_image_url %}<img src="{{ row.mvp_image_url }}" alt="{{ row.participant.mvp_card.name }}" class="w-8 h-auto rounded inline-block mr-1" />{% endif %}
              {{ row.participant.mvp_card.name|default:"-" }}
            </td>
          </tr>
          {% endfor %}
        </tbody>
      </table>
    </div>
  </div>

</div>
{% endblock %}
```

Atualizar a nav em `templates/base.html`, adicionando o link "Partidas":

```html
        <nav class="flex items-center gap-6 text-sm font-medium text-gray-600">
          <a
            href="{% url 'core:dashboard' %}"
            class="text-gray-900 font-semibold"
            >Dashboard</a
          >
          <a href="{% url 'core:game-list' %}" class="hover:text-gray-900 transition"
            >Partidas</a
          >
        </nav>
```

- [ ] **Step 2: Verificar**

```bash
.venv/bin/python -c "
import django, os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings.local')
django.setup()
from django.test import Client
from django.test.utils import setup_test_environment
from apps.core.models import Game
setup_test_environment()
c = Client()
print('lista:', c.get('/games/').status_code)
game = Game.objects.first()
print('detalhe:', c.get(f'/games/{game.id}/').status_code)
print('dashboard:', c.get('/').status_code)
"
```

Esperado: `lista: 200`, `detalhe: 200`, `dashboard: 200` — esta última confirma que a Task 10 (que já usa `core:game-detail`/`core:player-profile`) agora resolve sem `NoReverseMatch`. Se a Task 10 ainda não tiver sido feita, rode-a agora e verifique de novo.

- [ ] **Step 3: Commit**

```bash
git add apps/core/templates/core/game_list.html apps/core/templates/core/game_detail.html templates/base.html
git commit -m "Add game list/detail templates and Partidas nav link"
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
from apps.core.models import Game, Player
setup_test_environment()
c = Client()
game = Game.objects.first()
player = Player.objects.first()
print('/            ->', c.get('/').status_code)
print('/games/      ->', c.get('/games/').status_code)
print(f'/games/{game.id}/ ->', c.get(f'/games/{game.id}/').status_code)
print(f'/players/{player.id}/ ->', c.get(f'/players/{player.id}/').status_code)
print('/admin/      ->', c.get('/admin/').status_code)
"
grep -rn 'href="/admin/"' apps/ templates/ || echo "sem links pro admin"
```

Esperado: `check` sem issues, `makemigrations --check` sem diffs pendentes, as 4 rotas novas/existentes retornando `200`, `/admin/` retornando `404`, e a mensagem "sem links pro admin".
