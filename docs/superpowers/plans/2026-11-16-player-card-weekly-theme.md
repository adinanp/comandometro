# Card do Jogador + Tema da Semana — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** No dashboard de cada pod, um card lateral "Você no pod" com a performance do jogador logado, a zona de conforto dele e um Tema da Semana pessoal (fora da zona de conforto) que pode ser trocado 2 vezes por semana.

**Architecture:** Temas de cada comandante ficam em `Card` (buscados no EDHREC ao criar deck e pela sync manual). `PlayerWeeklyTheme` guarda uma linha por tema sorteado; use cases calculam elegibilidade, atribuição e troca. `PlayerPodCardUseCase` calcula as métricas; o `DashboardView` monta o card numa coluna lateral.

**Tech Stack:** Django 6.1, Postgres, Django `TestCase`, urllib (padrão dos clientes EDHREC/Scryfall), Tailwind CDN.

**Spec:** `docs/superpowers/specs/2026-11-16-player-card-weekly-theme-design.md`

## Global Constraints

- Esta branch parte do PR #1 (`Theme`, `EdhrecThemeClient`, `SyncEdhrecThemesUseCase`, `EnsureThemeSummaryUseCase`, `week_start` em `apps/core/use_cases/draw_themes.py`). Reusar, não duplicar.
- Código em inglês; textos de tela, URLs e mensagens em pt-BR.
- Views CBV finas com `PodMemberRequiredMixin`; lógica em use cases (`BaseUseCase`, `perform_request`, chamados via `.execute()`); um arquivo por classe em `apps/core/{models,views,use_cases}/`, reexportado no `__init__.py`.
- Testes rodam por módulo (sem `apps/__init__.py`, `manage.py test` acha 0): `python manage.py test apps.cards.tests apps.cards.tests_edhrec apps.core.tests apps.core.tests_theme_draw apps.core.tests_player_card apps.pods.tests`. Nenhum teste faz rede.
- `MAX_REROLLS_PER_WEEK = 2`, `RECENT_WEEKS_EXCLUDED = 4`, `COMFORT_THEMES_PER_COMMANDER = 5`.
- Semana = `week_start(now).date()` (segunda, America/Sao_Paulo).
- Dashboard nunca chama EDHREC nem espera LLM. Salvar deck nunca falha por causa do EDHREC.
- O card usa sempre o histórico todo (ignora `?days=`).

## Review Focus

1. **Partidas cujo deck foi apagado** (`GameParticipant.deck` é `SET_NULL`): as métricas contam a partida, o deck de conforto ignora a participação sem deck, nada quebra. → teste na Task 5.
2. **Troca com o dashboard filtrado** (`?days=7`): o redirect volta para `?days=7`. → teste na Task 6.
3. **Página do comandante sem `panels.taglinks`** (200 com outro formato): lista vazia, `edhrec_themes_synced_at` preenchido, sem exceção. → teste na Task 1.
4. **Ranking com empate e jogadores sem partidas**: posição em formato competição (1, 2, 2, 4); jogador sem partidas aparece com 0 pontos e posição válida. → teste na Task 5.
5. **Catálogo inteiro na zona de conforto + 4 semanas**: o relaxamento acha um tema que não saiu nesta semana; se até isso acabar, `None` (bloco escondido) em vez de erro. → teste na Task 4.

---

### Task 1: Temas do comandante no `Card` + cliente EDHREC

**Files:**
- Modify: `apps/cards/models.py` (`Card`), migração nova em `apps/cards/migrations/`
- Modify: `apps/cards/edhrec.py`
- Create: `apps/cards/use_cases/commander_themes.py`; Modify: `apps/cards/use_cases/__init__.py`
- Create: `apps/cards/test_data/edhrec_commander_atraxa.json` (reduzido: `panels.taglinks` com 7 itens, resto removido)
- Test: `apps/cards/tests_edhrec.py`, `apps/cards/tests.py`

**Interfaces:**
- Produces:
  - `Card.edhrec_theme_slugs` (JSONField, default list, blank), `Card.edhrec_themes_synced_at` (DateTimeField null, blank).
  - `edhrec_commander_slug(name: str) -> str` (módulo `apps/cards/edhrec.py`).
  - `EdhrecThemeClient.commander_theme_slugs(card_name: str, limit: int = 5) -> list[str]` — 404 → `[]`; outros erros → `EdhrecError`. `EdhrecThemeClient.parse_commander_theme_slugs(payload: dict, limit: int) -> list[str]`.
  - `EnsureCommanderThemesUseCase(BaseUseCase).perform_request(cards: Iterable[Card], client: EdhrecThemeClient | None = None, refresh: bool = False) -> int` (nº de cartas atualizadas). Pula cartas com `edhrec_themes_synced_at` preenchido, a menos que `refresh`. Por carta: sucesso (inclusive `[]`) → salva slugs + `synced_at`; `EdhrecError` ou qualquer exceção → loga e segue sem salvar.
  - `COMFORT_THEMES_PER_COMMANDER = 5` em `commander_themes.py`.

- [ ] **Step 1: Capture a fixture** com `curl -s -A "Comandometro/1.0" https://json.edhrec.com/pages/commanders/atraxa-praetors-voice.json`, mantendo só `{"panels": {"taglinks": [...7 itens]}}`.
- [ ] **Step 2: Write failing tests**
  - `test_commander_slug`: `"Atraxa, Praetors' Voice"` → `"atraxa-praetors-voice"`; `"Lim-Dûl the Necromancer"` → `"lim-dul-the-necromancer"`; `"Esika, God of the Tree // The Prismatic Bridge"` → `"esika-god-of-the-tree"`; `"Y'shtola, Night's Blessed"` → `"yshtola-nights-blessed"`.
  - `test_parse_commander_theme_slugs`: fixture → os 5 primeiros slugs em ordem (`["infect", "plus-1-plus-1-counters", "planeswalkers", "proliferate", "phyrexians"]` — confirmar contra a fixture capturada).
  - `test_parse_without_taglinks_returns_empty` (**Review Focus 3**): `{}` e `{"panels": {}}` → `[]`.
  - `test_commander_404_returns_empty`: `urlopen` levanta `HTTPError(code=404)` → `[]`; `HTTPError(500)` → `EdhrecError`.
  - `EnsureCommanderThemesTests` (cliente fake): salva slugs e `synced_at`; `[]` também marca `synced_at`; carta já sincronizada não é buscada sem `refresh`; com `refresh=True` é; exceção numa carta não impede a próxima e não marca `synced_at`.
- [ ] **Step 3:** rodar os dois módulos → FAIL (ImportError).
- [ ] **Step 4: Implement.** Slug: `unicodedata.normalize("NFKD")` + remover diacríticos, minúsculas, remover `'` e `,`, `[^a-z0-9]+` → `-`, `strip("-")`; dupla face → antes de `" // "`. `_get_json` precisa distinguir 404 (`urllib.error.HTTPError` com `code == 404`) antes do except genérico. `makemigrations cards`.
- [ ] **Step 5:** rodar → PASS.
- [ ] **Step 6: Commit** `"Store EDHREC themes per commander card"`.

---

### Task 2: Sync manual busca temas dos comandantes

**Files:**
- Modify: `apps/cards/use_cases/sync_themes.py`, `apps/cards/management/commands/sync_edhrec_themes.py`
- Test: `apps/cards/tests.py` (`SyncCommanderThemesTests`)

**Interfaces:**
- Consumes: `EnsureCommanderThemesUseCase` (Task 1).
- Produces: `SyncEdhrecThemesUseCase.perform_request(client=None, only=None, delay=0.2, refresh_commanders=False) -> dict` — resultado ganha a chave `"commanders": int` (cartas atualizadas). Comando ganha `--refresh-commanders`.

- [ ] **Step 1: Write failing tests** (`EnsureCommanderThemesUseCase.perform_request` mockado):
  - `test_sync_ensures_themes_of_deck_commanders`: 2 decks (pods diferentes) com 3 comandantes distintos + 1 carta comandante fora de deck → chamado uma vez com exatamente as 3 cartas e `refresh=False`.
  - `test_refresh_commanders_flag`: `refresh_commanders=True` → `refresh=True`.
  - `test_only_skips_commander_step`: `only="voltron"` → não chamado.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3: Implement**: etapa final com `Card.objects.filter(decks_as_commander__isnull=False).distinct()`; repassa `delay` para respeitar ~5 req/s (adicionar parâmetro `delay: float = 0` ao `EnsureCommanderThemesUseCase` se necessário — dorme entre buscas reais). Comando imprime `"<n> comandantes atualizados"`.
- [ ] **Step 4:** rodar → PASS.
- [ ] **Step 5: Commit** `"Sync commander themes in sync_edhrec_themes"`.

---

### Task 3: Buscar temas ao criar deck

**Files:**
- Modify: `apps/core/views/deck_create.py` (`form_valid`), `apps/core/views/deck_create_ajax.py`
- Test: `apps/core/tests_player_card.py` (criar; `DeckCreateCommanderThemesTests`)

**Interfaces:**
- Consumes: `EnsureCommanderThemesUseCase` (Task 1), com timeout curto: `EdhrecThemeClient(timeout=3)`.

- [ ] **Step 1: Write failing tests** (POST nos dois fluxos de criação; `EdhrecThemeClient.commander_theme_slugs` mockado):
  - `test_creating_deck_fetches_missing_commander_themes`: comandante sem dados → slugs salvos na carta.
  - `test_creating_deck_skips_commanders_already_synced`: carta com `synced_at` → mock não chamado.
  - `test_edhrec_down_still_creates_deck`: mock levanta `EdhrecError` → deck criado, resposta normal (redirect / JSON 200), carta sem `synced_at`.
  - Mesmos três para `deck-create-ajax` (pode ser `subTest` por URL).
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3: Implement**: depois do `save()` (fora de transação/signal), `EnsureCommanderThemesUseCase().execute(deck.commanders.all(), client=EdhrecThemeClient(timeout=3))` dentro de `try/except Exception` com log — a view nunca propaga.
- [ ] **Step 4:** rodar → PASS; suíte inteira → PASS.
- [ ] **Step 5: Commit** `"Fetch commander themes when a deck is created"`.

---

### Task 4: `PlayerWeeklyTheme` + atribuição e troca

**Files:**
- Create: `apps/core/models/player_weekly_theme.py`; Modify: `apps/core/models/__init__.py`; migração `apps/core`
- Create: `apps/core/use_cases/weekly_theme.py` (`eligible_weekly_themes`, `EnsureWeeklyThemeUseCase`, `RerollWeeklyThemeUseCase`); Modify: `apps/core/use_cases/__init__.py`
- Test: `apps/core/tests_player_card.py` (`WeeklyThemeTests`)

**Interfaces:**
- Consumes: `week_start` (`draw_themes.py`), `Card.edhrec_theme_slugs` (Task 1), `Theme`.
- Produces:
  - `PlayerWeeklyTheme(player FK Player CASCADE related "weekly_themes", theme FK cards.Theme PROTECT, week_start DateField, created_at auto)`; `ordering = ["-created_at"]`; `Index(fields=["player", "week_start"])`; `unique_together = ("player", "week_start", "theme")`.
  - `MAX_REROLLS_PER_WEEK = 2`, `RECENT_WEEKS_EXCLUDED = 4`.
  - `comfort_theme_slugs(player) -> set[str]` — união de `edhrec_theme_slugs` dos comandantes de `Deck.objects.filter(player=player)`.
  - `eligible_weekly_themes(player, week: date) -> QuerySet[Theme]` — com relaxamento: (a) − conforto − temas de `week_start >= week - 7*(RECENT_WEEKS_EXCLUDED-1) dias`; se vazio (b) − conforto − temas desta semana; se vazio (c) − temas desta semana; pode ser vazio.
  - `EnsureWeeklyThemeUseCase.perform_request(player, now=None) -> dict | None` → `{"theme": Theme, "rerolls_left": int}`; `None` se não há tema possível.
  - `RerollWeeklyThemeUseCase.perform_request(player, now=None) -> dict | None` → mesmo formato; `ValidationError("Você já usou as 2 trocas desta semana.")` sem trocas; sem linha na semana → age como `Ensure` (não gasta troca).
  - Ambos em `transaction.atomic()` com `Player.objects.select_for_update().get(pk=player.pk)`.

- [ ] **Step 1: Write failing tests** (temas criados em massa; `edhrec_theme_slugs` em cartas comandantes de decks do jogador):
  - `test_never_draws_comfort_zone_theme`: 10 temas, 9 na zona de conforto → sorteia o 10º.
  - `test_deck_without_commander_data_does_not_break`: cartas com `[]` → sorteia normalmente.
  - `test_first_visit_creates_one_row_second_does_not`.
  - `test_excludes_themes_from_last_four_weeks`: linhas em `week - 7`, `-14`, `-21` excluídas; em `-28` volta a ser elegível.
  - `test_reroll_twice_then_blocked`: 2 trocas → 3 linhas distintas, `rerolls_left` 1 → 0; 3ª levanta `ValidationError` e não cria linha.
  - `test_reroll_never_repeats_this_week`: 4 temas fora do conforto → 3 linhas, todas diferentes.
  - `test_rerolls_reset_next_week` e `test_week_boundary_sao_paulo`: `now` domingo 2026-11-15 23:30 SP vs segunda 2026-11-16 00:30 SP caem em semanas diferentes.
  - `test_reroll_without_row_acts_as_first_draw`: sem linha → cria 1, `rerolls_left == 2`.
  - `test_relaxes_rules_when_nothing_eligible` (**Review Focus 5**): todos os temas no conforto → ainda sorteia (relaxa); depois de esgotar os temas da semana → `Ensure` com tudo usado devolve o tema atual; `Reroll` sem candidatos devolve `None` sem criar linha e sem gastar troca.
  - `test_empty_catalog_returns_none`.
- [ ] **Step 2:** `python manage.py test apps.core.tests_player_card` → FAIL.
- [ ] **Step 3: Implement** model + migração + use cases.
- [ ] **Step 4:** rodar → PASS.
- [ ] **Step 5: Commit** `"Add weekly theme per player with rerolls"`.

---

### Task 5: Métricas do card (`PlayerPodCardUseCase`)

**Files:**
- Create: `apps/core/use_cases/player_stats.py` (helpers compartilhados), `apps/core/use_cases/player_pod_card.py`; Modify: `apps/core/use_cases/player_profile.py` (passa a usar os helpers), `apps/core/use_cases/__init__.py`
- Test: `apps/core/tests_player_card.py` (`PlayerPodCardTests`)

**Interfaces:**
- Produces:
  - `player_stats.favorite_color_combo(player) -> dict | None`, `player_stats.favorite_wincon(performances) -> dict | None` — movidos de `PlayerProfileUseCase` sem mudar comportamento (os métodos privados do perfil passam a delegar).
  - `PlayerPodCardUseCase.perform_request(player) -> dict` com chaves `games`, `wins`, `win_rate`, `points`, `points_rank`, `streak` (`{"kind": "wins"|"winless", "count": int}` ou `None`), `first_bloods`, `comfort_deck` (`{"deck": Deck, "games": int, "share": float}` ou `None`), `favorite_color_combo`, `favorite_wincon`.

- [ ] **Step 1: Write failing tests**:
  - `test_win_rate_and_points`: 4 partidas (1º, 2º, 3º, 4º) → `wins 1`, `win_rate 25.0`, `points 7`.
  - `test_points_rank_competition_with_ties` (**Review Focus 4**): pontos A=10, B=7, C=7, D=0 (D sem partidas) → ranks 1, 2, 2, 4.
  - `test_streak_wins` / `test_streak_winless`: ordem por `game.date` desc e `id` desc; partida sem data conta por último; sem partidas → `None`.
  - `test_first_bloods`: 2 games com `first_blood_player=player`.
  - `test_comfort_deck_share`: 5 partidas, 3 com deck X → X, `share 60.0`.
  - `test_comfort_deck_ignores_deleted_deck` (**Review Focus 1**): participação com `deck=None` conta em `games` mas não no deck de conforto.
  - `test_no_games`: tudo zerado/`None`, sem exceção.
  - Rodar `apps.core.tests` existentes para garantir que o perfil não mudou.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3: Implement** (pontos com `POINTS_BY_PLACEMENT` de `pod_insights.py`; ranking sobre todos os `Player` do pod).
- [ ] **Step 4:** rodar `apps.core.tests apps.core.tests_player_card` → PASS.
- [ ] **Step 5: Commit** `"Add player pod card metrics"`.

---

### Task 6: Card no dashboard, troca e resumo

**Files:**
- Modify: `apps/core/views/dashboard.py`, `apps/core/templates/core/dashboard.html`
- Create: `apps/core/templates/core/_player_card.html`, `apps/core/views/weekly_theme.py` (`RerollWeeklyThemeView`, `WeeklyThemeSummaryView`); Modify: `apps/core/views/__init__.py`, `apps/core/urls.py`
- Test: `apps/core/tests_player_card.py` (`PlayerCardViewTests`)

**Interfaces:**
- Consumes: `PlayerPodCardUseCase` (Task 5), `EnsureWeeklyThemeUseCase`/`RerollWeeklyThemeUseCase` (Task 4), `EnsureThemeSummaryUseCase` (PR #1).
- Produces: URLs `core:weekly-theme-reroll` → `meu-tema/trocar/` (POST), `core:weekly-theme-summary` → `meu-tema/resumo/` (GET JSON `{"summary": str|None}`). Contexto do dashboard: `player_card` (dict do Task 5 ou `None`), `weekly_theme` (dict do Task 4 ou `None`), `weekly_theme_summary_url`.

- [ ] **Step 1: Write failing tests**:
  - `test_card_shows_for_member_with_player`: contém "Você no pod", win rate, nome do deck de conforto, nome do tema, "2 trocas".
  - `test_no_player_no_card`: membro sem `Player` → 200 sem "Você no pod".
  - `test_dashboard_does_not_call_edhrec_or_llm`: patch em `urllib.request.urlopen` e `apps.cards.llm.generate_text` → não chamados.
  - `test_reroll_post_changes_theme_and_redirects`: tema muda, `rerolls_left` 1, redirect para o dashboard.
  - `test_reroll_preserves_days_filter` (**Review Focus 2**): POST com `days=7` → redirect para `...?days=7`.
  - `test_reroll_without_rerolls_shows_message`: terceira troca → mensagem de erro na página seguinte, tema igual.
  - `test_non_member_404` nas duas URLs novas; `test_reroll_get_not_allowed` (405).
  - `test_summary_endpoint_returns_current_theme_summary` (mock de `EnsureThemeSummaryUseCase.perform_request`).
  - `test_card_without_catalog_hides_theme_block`.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3: Implement.** Layout: envolver o conteúdo atual num grid `lg:grid-cols-[minmax(0,1fr)_320px]`; card em `<aside>` `lg:sticky lg:top-6`, renderizado **antes** do conteúdo no DOM e posicionado à direita no `lg` (`lg:order-last`), para ficar em cima no celular. Botão ⟳ = `<form method="post">` com `csrf_token` e `<input type="hidden" name="days">`; desabilitado com texto "0 trocas" quando acabar. Resumo: mesmo padrão `data-summary-url` + `fetch` do `theme_draw_detail.html`.
- [ ] **Step 4:** rodar a suíte inteira → PASS.
- [ ] **Step 5: Verificação no navegador**: dashboard com card à direita no desktop e em cima no celular (`resize_window` mobile); trocar duas vezes; terceira mostra mensagem.
- [ ] **Step 6: Commit** `"Show player card with weekly theme on the dashboard"`.

---

## Ordem e dependências

1 → 2, 1 → 3, 1 → 4 → 6, 5 → 6. Tasks 2, 3, 4 e 5 são independentes entre si depois da 1.
