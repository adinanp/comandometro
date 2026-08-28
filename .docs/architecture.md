# Arquitetura — Padrões Adotados

Este arquivo documenta os padrões que **já existem no código**, com
referência direta aos arquivos/classes/métodos reais. Se um exemplo daqui
não bater mais com o código, o código está certo — atualize este arquivo.

## Models carregam lógica de domínio

Os models não são apenas containers de campos: regras de negócio simples
vivem neles, e sinais do Django cobrem efeitos colaterais entre models.

- [`Deck.clean()`](../apps/core/models/deck.py) valida a regra "no máximo 2
  comandantes por deck".
- [`Deck.update_color_identity()`](../apps/core/models/deck.py) recalcula a
  identidade de cor combinada dos comandantes (ordenada em WUBRG) e salva
  via `update_fields=["color_identity"]`.
- [`Deck.display_commanders()`](../apps/core/models/deck.py) formata os
  nomes dos comandantes pra exibição.
- O signal `m2m_changed` (`update_deck_color_identity`, plugado em
  `Deck.commanders.through`) chama `update_color_identity()`
  automaticamente sempre que os comandantes de um deck mudam
  (`post_add`/`post_remove`/`post_clear`) — ninguém precisa lembrar de
  recalcular isso manualmente.
- [`Achievement.clean()`](../apps/core/models/achievement.py) herda a
  `date` do `Game` vinculado quando ela não é informada.

Em contraste, `Player`, `Card`, `Game` e `GameParticipant` são
intencionalmente modelos de dados simples, sem lógica de domínio — não é
esquecimento, é porque eles não têm nenhuma regra a proteger.

## Views são Class-Based

Hoje existe uma única view no projeto:
[`DashboardView(TemplateView)`](../apps/core/views/dashboard.py),
sobrescrevendo `get_context_data`.

> **Ponto de atenção:** toda a lógica de agregação do dashboard (ranking de
> jogadores, win rate %, porcentagem de wincon, MVP) está hoje dentro de
> `get_context_data`. Isso é o alvo do refactor de "camada de use cases"
> descrito em [conventions.md](./conventions.md) — ainda não implementado.
> Quando for extraído, a view deve ficar só chamando o use case e montando
> o contexto.

## Admin: padrões reutilizáveis

[`apps/core/admin.py`](../apps/core/admin.py) concentra várias
customizações do Django Admin que valem a pena reaproveitar em telas
futuras:

- `DeckAdminForm` — esconde/desabilita o campo `player` condicionalmente
  quando ele já veio via query param.
- Inlines (`GameParticipantInline`, `AchievementInline`,
  `PlayerProfileInline`) e `formfield_for_foreignkey` sobrescrito pra
  desabilitar o "+" de adicionar `mvp_card` direto do inline.
- `GameAdmin.get_urls()` + `get_player_decks()` — endpoint JSON próprio
  dentro do admin, sem precisar de uma app/API separada.
- `class Media: js = (...)` — como acoplar JS customizado a uma tela do
  admin.
- `CardAdmin` como somente-leitura (`has_add_permission`,
  `has_change_permission`, `has_delete_permission` retornando `False`) —
  cartas só devem ser criadas/atualizadas via `import_mtgjson`.
- `DeckAdmin.get_fields` / `get_changeform_initial_data` / `save_model` —
  como prefixar um campo a partir de um query param (usado no fluxo de
  "criar deck a partir da tela do jogador").

## Settings, env e logging

- Settings divididos em `config/settings/base.py` / `local.py` /
  `production.py` — `local.py` e `production.py` fazem `from .base import
  *` e só ajustam o que muda por ambiente (`DEBUG`, hardening de
  segurança). `config/settings/__init__.py` reexporta de `.local` como
  default de desenvolvimento.
- `django-environ` (`environ.Env()` + `read_env(BASE_DIR / ".env")`) pra
  ler variáveis de ambiente; `dj-database-url` monta `DATABASES` a partir
  de `DATABASE_URL`. Veja [.env.example](../.env.example) pra saber quais
  variáveis existem.
- `LOGGING` configurado em `base.py`: um handler de console + um logger de
  namespace `apps` (cobre `apps.core.*` por herança do próprio módulo
  `logging`) e um logger `django` — ambos com nível configurável via env
  (`APP_LOG_LEVEL`, `DJANGO_LOG_LEVEL`). Uso de referência em
  [`import_mtgjson.py`](../apps/core/management/commands/import_mtgjson.py).
- Hardening de produção em `production.py`: `ALLOWED_HOSTS` vem do env,
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` e `SECURE_SSL_REDIRECT`
  ligados (assume produção atrás de HTTPS). `local.py` não tem esse
  hardening — dev roda em HTTP puro.
