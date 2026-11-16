# Sorteio de Temas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Um membro do pod sorteia 4 temas do EDHREC distintos para 4 jogadores, vê um card por jogador (nº de decks, top 3 comandantes, resumo pt-BR) e compartilha uma imagem 1080×1350.

**Architecture:** Catálogo global `Theme` em `apps/cards`, carregado por `sync_edhrec_themes` (EDHREC + Scryfall), nunca consultado online no sorteio. `ThemeDraw`/`ThemeDrawSeat` em `apps/core`, escopados por pod. Resumo via Gemini gerado sob demanda (endpoint JSON chamado por `fetch`) e salvo no `Theme`. Recap renderizado com Pillow a cada request.

**Tech Stack:** Django 6.1, Postgres, Django `TestCase` (`python manage.py test`), Pillow, google-genai, urllib (padrão do cliente Scryfall existente), Tailwind CDN nos templates.

**Spec:** `docs/superpowers/specs/2026-11-16-theme-draw-design.md`

## Global Constraints

- Código (nomes, classes) em inglês; textos de tela, URLs e mensagens em pt-BR.
- `apps/cards` = dado global, nunca filtrado por pod. `apps/core` = tudo escopado por pod.
- Views CBV finas herdando `PodMemberRequiredMixin` (`apps/pods/mixins.py`); lógica em use cases herdando `apps.core.use_cases.base.BaseUseCase` (`perform_request`), chamados via `.execute()`.
- `apps/core/models/`, `views/`, `use_cases/`: um arquivo por classe, reexportado no `__init__.py` do pacote. `apps/cards` usa um único `models.py`.
- Sempre 4 jogadores por sorteio.
- Resumo: pt-BR, no máximo **120 caracteres**, cortado na última palavra inteira + "…".
- Semana do sorteio: segunda 00:00 a domingo 23:59 em `America/Sao_Paulo`; `TIME_ZONE` do projeto continua `"UTC"`.
- EDHREC: `https://json.edhrec.com/pages/tags.json` e `https://json.edhrec.com/pages/tags/<slug>.json`; ≤5 req/s; User-Agent `Comandometro/1.0`.
- O sorteio e as páginas **nunca** chamam EDHREC. A imagem **nunca** chama o Gemini.
- Imagem 1080×1350; downloads de arte em paralelo com prazo total de ~10 s; sem título, sem data, sem cores.
- Env: `GEMINI_API_KEY` (sem ela, sem resumo e sem erro), `GEMINI_MODEL` (opcional).
- Nenhum teste faz rede: mockar `urllib.request.urlopen` / o cliente Gemini.

## Review Focus

1. **Tema sem top comandantes** (página do EDHREC sem a lista `topcommanders`, ou sync falhou): card e imagem renderizam sem comandante e sem arte, sem exceção. → teste na Task 7 (view) e Task 8 (recap).
2. **Nomes longos** (apelido de jogador com 40+ caracteres, tema "Commander Matters", comandante "Frodo, Adventurous Hobbit // Sam, Loyal Attendant"): a imagem corta com "…" dentro da linha, nada vaza para fora do bloco. → teste na Task 8.
3. **Resposta suja do Gemini** (aspas envolvendo o texto, quebras de linha, prefixo "Resumo:", >120 chars): salva uma linha limpa ≤120. → teste na Task 6.
4. **Endpoint de resumo com tema que não está no draw, ou draw de outro pod**: 404, e o Gemini não é chamado. → teste na Task 7.
5. **Form com 3 ou 5 jogadores, jogador repetido, ou id de jogador de outro pod**: erro de validação, nenhum `ThemeDraw` criado. → teste na Task 7.

---

### Task 1: Model `Theme` + formatação do nº de decks

**Files:**
- Modify: `apps/cards/models.py` (adicionar `Theme`)
- Create: migração `apps/cards/migrations/00XX_theme.py` (via `makemigrations`)
- Modify: `apps/cards/admin.py` (registrar `Theme` somente-leitura, como `CardAdmin`)
- Test: `apps/cards/tests.py` (criar)

**Interfaces:**
- Produces: `apps.cards.models.Theme` com campos `slug` (CharField 120, unique), `name` (CharField 120), `num_decks` (PositiveIntegerField, default 0), `popularity_rank` (PositiveIntegerField, default 0), `top_commanders` (JSONField, default list — itens `{"name": str, "num_decks": int}`), `art_crop_url` (URLField, blank), `summary` (CharField 160, blank), `summary_model` (CharField 80, blank), `summary_generated_at` (DateTimeField null), `edhrec_synced_at` (DateTimeField null); `Meta.ordering = ["popularity_rank", "name"]`; `__str__` → `name`.
- Produces: `Theme.top_commander_names(limit: int = 3) -> list[str]`; `Theme.display_num_decks() -> str`.

- [ ] **Step 1: Write the failing tests** em `apps/cards/tests.py`, classe `ThemeModelTests(TestCase)`:
  - `test_display_num_decks_thousands`: `num_decks=62437` → `"62,4 mil decks"`; `num_decks=168250` → `"168,3 mil decks"`.
  - `test_display_num_decks_round_thousand`: `num_decks=5000` → `"5 mil decks"` (sem ",0").
  - `test_display_num_decks_below_thousand`: `7` → `"7 decks"`; `1` → `"1 deck"`.
  - `test_top_commander_names_limits_and_handles_empty`: `top_commanders=[{"name":"A","num_decks":3},{"name":"B",...},{"name":"C",...},{"name":"D",...}]` → `["A","B","C"]`; `top_commanders=[]` → `[]`.
- [ ] **Step 2:** `python manage.py test apps.cards` → FAIL (ImportError `Theme`).
- [ ] **Step 3: Implement `Theme`** com os campos acima e os dois métodos. `display_num_decks`: ≥1000 → `num_decks/1000` com 1 casa, vírgula decimal, sem ",0"; <1000 → inteiro, singular para 1.
- [ ] **Step 4:** `python manage.py makemigrations cards` e `python manage.py test apps.cards` → PASS.
- [ ] **Step 5: Commit** `git commit -m "Add Theme catalog model"`.

---

### Task 2: `EdhrecThemeClient` (parsing do EDHREC)

**Files:**
- Create: `apps/cards/edhrec.py`
- Create: `apps/cards/test_data/edhrec_tags.json` (reduzido: 3 itens) e `apps/cards/test_data/edhrec_tag_voltron.json` (reduzido: lista `topcommanders` com 4 itens + uma lista `topcards` irrelevante)
- Test: `apps/cards/tests_edhrec.py`

**Interfaces:**
- Produces:
  - `@dataclass ThemeListing(slug: str, name: str, num_decks: int, popularity_rank: int)`
  - `class EdhrecError(Exception)`
  - `class EdhrecThemeClient:` `list_themes() -> list[ThemeListing]`; `top_commanders(slug: str, limit: int = 10) -> list[dict]` (itens `{"name", "num_decks"}`). Ambos levantam `EdhrecError` em erro de rede/HTTP/JSON. Métodos estáticos de parsing testáveis sem rede: `parse_theme_list(payload: dict) -> list[ThemeListing]`, `parse_top_commanders(payload: dict, limit: int) -> list[dict]`.

- [ ] **Step 1: Capture as fixtures** com `curl -s -A "Mozilla/5.0" https://json.edhrec.com/pages/tags.json` e `.../tags/voltron.json`, mantendo a estrutura (`container.json_dict.cardlists[].cardviews[]`) e cortando os itens. Confirme aqui qual campo traz a contagem de decks no catálogo (`num_decks` ou `count`) e registre no teste.
- [ ] **Step 2: Write the failing tests** (`EdhrecParsingTests`):
  - `test_parse_theme_list`: 3 `ThemeListing`, `slug` extraído de `url` `/tags/plus-1-plus-1-counters` → `"plus-1-plus-1-counters"`, `popularity_rank` 1,2,3 na ordem do JSON, `num_decks` correto.
  - `test_parse_top_commanders_uses_topcommanders_list_in_order`: 4 nomes em ordem, ignora `topcards`; `limit=2` → 2 itens.
  - `test_parse_top_commanders_missing_list_returns_empty`: payload sem `topcommanders` → `[]`.
  - `test_list_themes_wraps_network_error`: `urlopen` mockado levantando `URLError` → `EdhrecError`.
- [ ] **Step 3:** `python manage.py test apps.cards.tests_edhrec` → FAIL.
- [ ] **Step 4: Implement** em `apps/cards/edhrec.py` com `urllib.request` (mesmo estilo de `apps/cards/use_cases/card_image.py`), timeout 10 s, User-Agent `Comandometro/1.0`. O cliente não faz rate-limit (é do comando, Task 4).
- [ ] **Step 5:** testes → PASS.
- [ ] **Step 6: Commit** `"Add EDHREC theme client"`.

---

### Task 3: Resolver a arte (art crop) de um comandante

**Files:**
- Create: `apps/cards/use_cases/commander_art.py`; Modify: `apps/cards/use_cases/__init__.py` (exportar)
- Test: `apps/cards/tests.py` (`CommanderArtTests`)

**Interfaces:**
- Produces: `ResolveCommanderArtUseCase(BaseUseCase)`, `perform_request(commander_name: str) -> str | None` — URL do `art_crop`.

- [ ] **Step 1: Write the failing tests** (mock de `urllib.request.urlopen`):
  - `test_uses_first_card_of_partner_pair`: `"Frodo, Adventurous Hobbit // Sam, Loyal Attendant"` → a URL consultada contém `exact=Frodo%2C+Adventurous+Hobbit` (ou equivalente encoded) e não "Sam".
  - `test_returns_art_crop_from_image_uris`: resposta `{"image_uris": {"art_crop": "https://x/a.jpg"}}` → `"https://x/a.jpg"`.
  - `test_falls_back_to_first_face`: resposta só com `card_faces[0].image_uris.art_crop` → essa URL.
  - `test_network_error_returns_none`: `URLError` → `None`.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3: Implement**: `https://api.scryfall.com/cards/named?exact=<nome>` (urlencode), headers `SCRYFALL_HEADERS` de `card_image.py`, timeout 5 s. Pares `"A // B"` → `"A"`. Qualquer erro → `None` + `logger.warning`.
- [ ] **Step 4:** rodar → PASS.
- [ ] **Step 5: Commit** `"Resolve commander art crop from Scryfall"`.

---

### Task 4: Comando `sync_edhrec_themes`

**Files:**
- Create: `apps/cards/use_cases/sync_themes.py`; Modify: `apps/cards/use_cases/__init__.py`
- Create: `apps/cards/management/commands/sync_edhrec_themes.py`
- Test: `apps/cards/tests.py` (`SyncThemesTests`)

**Interfaces:**
- Consumes: `EdhrecThemeClient`, `ThemeListing`, `EdhrecError` (Task 2); `ResolveCommanderArtUseCase` (Task 3); `Theme` (Task 1).
- Produces: `SyncEdhrecThemesUseCase(BaseUseCase)`, `perform_request(client: EdhrecThemeClient | None = None, only: str | None = None, delay: float = 0.2) -> dict` com `{"themes": int, "ok": int, "failed": list[str]}`.

- [ ] **Step 1: Write the failing tests** (cliente fake injetado, `delay=0`, `ResolveCommanderArtUseCase.perform_request` mockado retornando `"https://x/art.jpg"`):
  - `test_upserts_catalog_and_details`: 2 temas listados → 2 `Theme` com `name`, `num_decks`, `popularity_rank`, `top_commanders`, `art_crop_url`, `edhrec_synced_at` preenchidos; rodar de novo com `num_decks` alterado atualiza sem duplicar.
  - `test_failed_detail_is_reported_and_others_continue`: `top_commanders` levanta `EdhrecError` para um slug → esse slug em `failed`, o outro sincronizado; o que falhou mantém `top_commanders` anterior.
  - `test_theme_missing_from_catalog_is_kept`: `Theme` existente que não está na lista nova continua no banco.
  - `test_only_syncs_single_slug_details`: `only="voltron"` → `top_commanders` chamado só para `voltron`.
  - `test_does_not_touch_summary`: `summary` existente fica igual.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3: Implement** o use case (`update_or_create` por `slug`; `time.sleep(delay)` entre chamadas de detalhe para ≤5 req/s; arte só quando há comandante nº 1 e o nome mudou ou `art_crop_url` vazio) e o comando (`--only <slug>`; imprime `"<ok>/<themes> temas sincronizados"` e lista falhas).
- [ ] **Step 4:** rodar → PASS.
- [ ] **Step 5: Smoke manual** `python manage.py sync_edhrec_themes --only voltron` → 1 sincronizado, `Theme(slug="voltron")` com comandantes e arte. (Rodar o catálogo inteiro fica a critério do dev, ~2 min.)
- [ ] **Step 6: Commit** `"Add sync_edhrec_themes command"`.

---

### Task 5: `ThemeDraw`, `ThemeDrawSeat` e `DrawThemesUseCase`

**Files:**
- Create: `apps/core/models/theme_draw.py` (`ThemeDraw`, `ThemeDrawSeat`); Modify: `apps/core/models/__init__.py`
- Create: migração `apps/core`
- Create: `apps/core/use_cases/draw_themes.py`; Modify: `apps/core/use_cases/__init__.py`
- Test: `apps/core/tests_theme_draw.py`

**Interfaces:**
- Consumes: `Theme` (Task 1).
- Produces:
  - `ThemeDraw`: `pod` FK `pods.Pod` (CASCADE, related `theme_draws`), `created_by` FK user (SET_NULL, null), `created_at` auto. `Meta.ordering = ["-created_at"]`.
  - `ThemeDrawSeat`: `draw` FK (CASCADE, related `seats`), `player` FK `Player` (CASCADE), `theme` FK `cards.Theme` (PROTECT), `position` PositiveSmallIntegerField; `unique_together` (`draw`,`player`), (`draw`,`theme`); `Meta.ordering = ["position"]`; `clean()` → `ValidationError` se `player.pod_id != draw.pod_id`.
  - `DrawThemesUseCase(BaseUseCase)`, `perform_request(pod, players: list[Player], created_by=None) -> ThemeDraw`. Levanta `ValidationError` se `len(set(players)) != 4`, se algum player não é do pod, ou se há menos de 4 `Theme` no banco.
  - `week_start(now: datetime) -> datetime` (módulo `draw_themes.py`): segunda 00:00 em `America/Sao_Paulo` da semana de `now`, timezone-aware.
  - Constante `PLAYERS_PER_DRAW = 4`.

- [ ] **Step 1: Write the failing tests:**
  - `test_seat_clean_rejects_player_from_other_pod`.
  - `test_week_start_sunday_night_brasilia`: `now = 2026-11-16 02:30 UTC` (domingo 23:30 em SP) → `week_start` = 2026-11-09 00:00 SP; `now = 2026-11-16 03:30 UTC` (segunda 00:30 SP) → 2026-11-16 00:00 SP.
  - `test_draw_creates_four_distinct_seats_in_order`: 10 temas → 4 seats, temas distintos, `position` 0..3 na ordem dos players recebidos.
  - `test_excludes_themes_drawn_this_week_in_same_pod`: 8 temas; um draw anterior desta semana no pod usou 4 → o novo usa exatamente os outros 4 (`random` real; determinístico pelo tamanho).
  - `test_ignores_other_pod_and_previous_week`: draw de outro pod e draw do mesmo pod com `created_at` na semana anterior (atualizar `created_at` via `.update()`) não excluem temas.
  - `test_falls_back_when_fewer_than_four_eligible`: 5 temas, 4 usados esta semana → novo draw com 4 temas distintos, sem erro.
  - `test_rejects_wrong_player_count_and_foreign_player`: 3 players, players repetidos, player de outro pod → `ValidationError`, `ThemeDraw.objects.count() == 0`.
  - `test_rejects_empty_catalog`: 0 temas → `ValidationError`.
- [ ] **Step 2:** `python manage.py test apps.core.tests_theme_draw` → FAIL.
- [ ] **Step 3: Implement** models + migração + use case (`transaction.atomic`; elegíveis = `Theme` excluindo `theme_id` de seats com `draw__pod=pod, draw__created_at__gte=week_start(timezone.now())`; se <4 elegíveis, completa com o restante; `random.sample`; `full_clean()` nos seats).
- [ ] **Step 4:** rodar → PASS; `python manage.py test` inteiro → PASS.
- [ ] **Step 5: Commit** `"Add theme draw models and draw use case"`.

---

### Task 6: Resumo via Gemini (`EnsureThemeSummaryUseCase`)

**Files:**
- Modify: `requirements/base.txt` (+ `google-genai` com versão fixa atual)
- Modify: `config/settings/base.py` (`GEMINI_API_KEY = env("GEMINI_API_KEY", default="")`, `GEMINI_MODEL = env("GEMINI_MODEL", default="gemini-2.5-flash")` — conferir o nome do Flash atual do plano grátis antes de fixar o default)
- Modify: `.env.example` (`GEMINI_API_KEY=`, `GEMINI_MODEL=`)
- Create: `apps/cards/llm.py`
- Create: `apps/cards/use_cases/theme_summary.py`; Modify: `apps/cards/use_cases/__init__.py`
- Test: `apps/cards/tests.py` (`ThemeSummaryTests`)

**Interfaces:**
- Consumes: `Theme` (Task 1).
- Produces:
  - `apps/cards/llm.py`: `class LlmError(Exception)`; `generate_text(prompt: str, *, model: str, api_key: str, timeout_s: float = 8.0) -> str` (google-genai `Client(api_key=...).models.generate_content`, timeout via `HttpOptions`; qualquer falha → `LlmError`).
  - `EnsureThemeSummaryUseCase(BaseUseCase)`, `perform_request(theme: Theme) -> str | None`.
  - `SUMMARY_MAX_CHARS = 120`; `clean_summary(raw: str, max_chars: int = SUMMARY_MAX_CHARS) -> str` (módulo `theme_summary.py`).
  - `build_summary_prompt(theme: Theme) -> str`.

- [ ] **Step 1: Write the failing tests** (`generate_text` mockado com `unittest.mock.patch("apps.cards.use_cases.theme_summary.generate_text")`; `override_settings(GEMINI_API_KEY="k")`):
  - `test_returns_cached_summary_without_calling_llm`.
  - `test_no_api_key_returns_none_without_calling_llm` (`GEMINI_API_KEY=""`).
  - `test_saves_summary_model_and_timestamp`.
  - `test_llm_error_returns_none_and_saves_nothing`.
  - `test_clean_summary_strips_noise` (**Review Focus 3**): `'"Resumo: Sacrifica criaturas\npor valor."'` → `"Sacrifica criaturas por valor."`; aspas tipográficas também.
  - `test_clean_summary_truncates_on_word_boundary`: texto de 200 chars → `len <= 120`, termina em `"…"`, não corta palavra no meio.
  - `test_prompt_is_grounded`: `build_summary_prompt` contém o nome do tema, os 3 primeiros comandantes, `"120"` e `"português"`.
  - `test_empty_llm_response_returns_none`: `generate_text` → `"   "` → `None`, nada salvo.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3: Implement.** Prompt em pt-BR: explicar em uma frase como o tema joga/vence, no máximo 120 caracteres, nomes de cartas em inglês, citar só cartas da lista dada, sem aspas nem prefixo. `clean_summary`: colapsa espaços/quebras, remove aspas retas/tipográficas nas pontas e prefixos `Resumo:`, trunca na última palavra inteira que caiba com `"…"`.
- [ ] **Step 4:** `pip install -r requirements/local.txt` e rodar → PASS.
- [ ] **Step 5: Commit** `"Generate theme summaries with Gemini"`.

---

### Task 7: Telas — criar sorteio, detalhe e endpoint de resumo

**Files:**
- Create: `apps/core/forms/theme_draw.py`; Modify: `apps/core/forms/__init__.py`
- Create: `apps/core/views/theme_draw_create.py`, `theme_draw_detail.py`, `theme_summary.py`; Modify: `apps/core/views/__init__.py`
- Modify: `apps/core/urls.py`
- Create: `apps/core/templates/core/theme_draw_form.html`, `theme_draw_detail.html`
- Modify: `templates/base.html` (link "Sorteio de temas" na navbar, ao lado de "Jogadores")
- Test: `apps/core/tests_theme_draw.py` (`ThemeDrawViewTests`)

**Interfaces:**
- Consumes: `DrawThemesUseCase`, `PLAYERS_PER_DRAW`, `ThemeDraw` (Task 5); `EnsureThemeSummaryUseCase` (Task 6); `Theme.top_commander_names`, `Theme.display_num_decks` (Task 1).
- Produces:
  - URLs (namespace `core`): `theme-draw-create` → `sorteio-de-temas/`; `theme-draw-detail` → `sorteio-de-temas/<int:pk>/`; `theme-summary` → `sorteio-de-temas/<int:pk>/resumo/<int:theme_id>/`; `theme-draw-recap` → `sorteio-de-temas/<int:pk>/recap.png` (rota registrada na Task 8).
  - `ThemeDrawForm(pod)`: `players = ModelMultipleChoiceField(CheckboxSelectMultiple, queryset=Player.objects.filter(pod=pod))`; `clean_players` exige exatamente 4. Erros de `DrawThemesUseCase` viram `form.add_error(None, ...)`.
  - `ThemeSummaryView.get` → `JsonResponse({"summary": str | None})`.

- [ ] **Step 1: Write the failing tests** (login com `Membership` + `force_login`, como `apps/core/tests.py`; `EnsureThemeSummaryUseCase.perform_request` mockado):
  - `test_non_member_gets_404` nas três URLs.
  - `test_post_with_four_players_creates_draw_and_redirects` → 302 para `theme-draw-detail`.
  - `test_invalid_selections_show_error` (**Review Focus 5**): 3 players, 5 players, id de player de outro pod → 200 com erro, `ThemeDraw.objects.count() == 0`.
  - `test_pod_with_fewer_than_four_players_shows_message`: GET mostra aviso "precisa de pelo menos 4 jogadores".
  - `test_empty_catalog_shows_friendly_error`: POST válido sem `Theme` → 200 com "catálogo de temas ainda não foi carregado".
  - `test_detail_shows_cards` : contém nome do jogador, nome do tema, `"62,4 mil decks"`, 3 nomes de comandante; o 4º não aparece.
  - `test_detail_with_theme_without_commanders` (**Review Focus 1**): `top_commanders=[]`, `art_crop_url=""` → 200.
  - `test_detail_marks_cards_without_summary_for_fetch`: card sem resumo tem `data-summary-url` apontando para `theme-summary`; card com resumo mostra o texto e não tem o atributo.
  - `test_summary_endpoint_returns_json` → `{"summary": "..."}`.
  - `test_summary_endpoint_rejects_theme_not_in_draw` (**Review Focus 4**): tema fora do draw → 404; draw de outro pod → 404; mock não chamado.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3: Implement** form, views (detalhe e endpoint buscam o draw com `ThemeDraw.objects.filter(pod=self.pod)`; endpoint usa `get_object_or_404(draw.seats, theme_id=theme_id)`), URLs, link na navbar e templates no estilo das páginas existentes (Tailwind). JS inline no detalhe: para cada `[data-summary-url]`, mostra "gerando resumo…", faz `fetch` GET, preenche o texto ou remove o bloco se `summary` for `null`/erro. Botão "Gerar imagem" fica para a Task 8.
- [ ] **Step 4:** rodar → PASS; `python manage.py test` → PASS.
- [ ] **Step 5: Verificação no navegador** (preview do dev server): criar sorteio com 4 jogadores, ver os cards e o resumo chegando (ou sumindo sem `GEMINI_API_KEY`).
- [ ] **Step 6: Commit** `"Add theme draw pages and summary endpoint"`.

---

### Task 8: Imagem do recap e compartilhamento

**Files:**
- Modify: `requirements/base.txt` (+ `Pillow` versão fixa atual)
- Create: `apps/core/static/core/fonts/` com `ArchivoBlack-Regular.ttf`, `Inter-Regular.ttf`, `Inter-SemiBold.ttf` e os `OFL.txt` (do repositório Google Fonts no GitHub)
- Create: `apps/core/use_cases/theme_draw_recap.py`; Modify: `apps/core/use_cases/__init__.py`
- Create: `apps/core/views/theme_draw_recap.py`; Modify: `apps/core/views/__init__.py`, `apps/core/urls.py`
- Modify: `apps/core/templates/core/theme_draw_detail.html` (botão + JS de share)
- Test: `apps/core/tests_theme_draw.py` (`ThemeDrawRecapTests`)

**Interfaces:**
- Consumes: `ThemeDraw`, seats (Task 5); campos de `Theme` (Task 1). **Não** usa `EnsureThemeSummaryUseCase`.
- Produces: `ThemeDrawRecapUseCase(BaseUseCase)`, `perform_request(draw: ThemeDraw) -> bytes` (PNG); helper `fit_text(draw, text, font, max_width, max_lines) -> list[str]` (quebra por largura medida, última linha com "…" se não couber). `ThemeDrawRecapView.get` → `HttpResponse(content_type="image/png")` com `Content-Disposition: inline; filename="sorteio-de-temas-<pk>.png"`.

Layout (pixels na imagem final, do mockup aprovado `layout-a-v2` × 2,5): fundo `#141210`; margem lateral 45; selo "SORTEIO DE TEMAS" (fundo `#e24c2c`, texto branco, Archivo Black ~25 px) em y=45; "POD <NOME DO POD>" em maiúsculas, `#e24c2c`, ~22 px, logo abaixo; 4 linhas de 260 px de altura, gap 15, fundo `#24201d`, começando em ~y=180; arte à esquerda 275 px de largura (crop `cover` para 275×260); texto à direita com padding 30: jogador (Archivo Black ~32 px) e nº de decks alinhado à direita (Inter ~20 px `#aaaaaa`), tema em maiúsculas (Archivo Black ~25 px `#f0c9a0`), "Top comandante: <nome>" (Inter ~19 px `#bbbbbb`), resumo (Inter ~20 px `#e8e2da`, até 2 linhas); rodapé a ~y=1305: "COMANDÔMETRO" à esquerda (Archivo Black ~25 px) e "sorteio de temas" à direita (Inter ~20 px `#aaaaaa`). Arte ausente → retângulo `#3a3430`.

- [ ] **Step 1: Write the failing tests** (download da arte mockado devolvendo um JPEG 10×10 gerado com Pillow em memória):
  - `test_recap_is_png_1080x1350`: abre os bytes com `PIL.Image.open` → `size == (1080, 1350)`, formato `PNG`.
  - `test_recap_does_not_call_gemini`: patch em `EnsureThemeSummaryUseCase.perform_request` e em `apps.cards.llm.generate_text` → não chamados.
  - `test_recap_survives_missing_art_and_commanders` (**Review Focus 1**): `art_crop_url=""`, `top_commanders=[]`, download levantando `URLError` → gera PNG.
  - `test_fit_text_truncates_long_names` (**Review Focus 2**): nickname de 60 chars, `max_lines=1`, `max_width=400` → 1 linha terminando em "…" e com largura medida ≤ 400; resumo de 120 chars com `max_lines=2` → ≤ 2 linhas, cada uma ≤ `max_width`.
  - `test_recap_view_requires_member_and_returns_png`: não-membro 404; membro → 200, `image/png`.
- [ ] **Step 2:** rodar → FAIL.
- [ ] **Step 3: Implement** use case (downloads com `concurrent.futures.ThreadPoolExecutor`, `wait(..., timeout=10)`, cada `urlopen` com timeout 8 s; fontes carregadas de `apps/core/static/core/fonts/` via caminho absoluto do módulo), view e rota `theme-draw-recap`. No template: botão "Gerar imagem" faz `fetch` do PNG → `File`; se `navigator.canShare?.({files:[file]})`, `navigator.share({files:[file]})`; senão baixa via `<a download>`.
- [ ] **Step 4:** rodar → PASS; `python manage.py test` → PASS.
- [ ] **Step 5: Verificação visual:** abrir `.../recap.png` no navegador com 4 temas reais (sincronizados com `--only`), comparar com o mockup aprovado; conferir corte de nome longo.
- [ ] **Step 6: Commit** `"Render and share theme draw recap image"`.

---

## Ordem e dependências

1 → 2 → 3 → 4 (catálogo); 5 depende de 1; 6 depende de 1; 7 depende de 5 e 6; 8 depende de 5 e 7. Tasks 2–4 e 5–6 podem ser feitas em qualquer ordem relativa entre si.
