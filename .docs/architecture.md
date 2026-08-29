# Arquitetura — Padrões Adotados

Este arquivo documenta os padrões que **já existem no código**, com
referência direta aos arquivos/classes/métodos reais. Se um exemplo daqui
não bater mais com o código, o código está certo — atualize este arquivo.

## Três apps, cada uma com uma responsabilidade

- `apps/cards/` — o catálogo de cartas de Magic (`Card`) e o comando
  `import_mtgjson`. Dado de referência global, igual pra todo mundo,
  **nunca** filtrado por pod.
- `apps/pods/` — multi-tenancy: `Pod`, `Membership`, convite, mixins de
  permissão (`PodMemberRequiredMixin`/`PodOwnerRequiredMixin`) e a
  integração com login (`django-allauth`).
- `apps/core/` — o domínio do jogo em si (`Player`, `Deck`, `Game`,
  `GameParticipant`, `Achievement`), sempre escopado por pod, mais
  dashboard/use_cases/views. Também é dono de `apps/core/use_cases/base.py`
  (`BaseUseCase`), infraestrutura comum que `apps/cards` e `apps/pods`
  também usam.

Não existe mais um pacote `shared/` — ele foi absorvido por `core`
(ver seção de Use Cases abaixo).

## Multi-tenancy: tudo pertence a um Pod

Um usuário pode participar de vários `Pod`s (cada um um playgroup
isolado, com seus próprios jogadores/decks/partidas). Só dois models têm
FK direta pra `Pod`:

- [`Player.pod`](../apps/core/models/player.py) (obrigatório) — raiz da
  árvore de dados de um pod.
- [`Game.pod`](../apps/core/models/game.py) (obrigatório) — não tem
  nenhum outro FK obrigatório de onde derivar o pod.

`Deck`, `GameParticipant` e `Achievement` **não** têm campo `pod`
próprio — o pod é sempre alcançável via relação existente
(`Deck.player.pod`, `GameParticipant.player.pod`/`game.pod`,
`Achievement.player.pod`). Isso evita denormalizar `pod` em toda tabela;
toda query de listagem filtra via `Model.objects.filter(pod=pod)` ou
`filter(player__pod=pod)`.

`GameParticipant.clean()` garante `player.pod_id == game.pod_id` —
protege contra vincular um jogador de um pod a uma partida de outro.

`Player.user` é opcional (`null=True`): um `Player` pode estar vinculado
a uma conta (`user`) ou ser um "convidado" sem login — as duas coisas
convivem no mesmo roster.

### Controle de acesso

[`apps/pods/mixins.py`](../apps/pods/mixins.py) tem os dois mixins que
toda view escopada por pod usa:

- `PodMemberRequiredMixin` — resolve o `Pod` a partir de `pod_slug` na
  URL, exige que `request.user` seja membro (senão, `404` — não revela
  que o pod existe pra quem não é membro), e expõe `self.pod` +
  `self.membership` **antes** do handler (`get`/`post`) rodar. Também
  injeta `pod`/`membership` no contexto do template via
  `get_context_data`.
- `PodOwnerRequiredMixin` — igual, mas exige `role=OWNER`. Usado só nas
  views de configuração do pod (renomear, regenerar convite, remover
  membro, apagar pod).

Toda view de `apps/core` herda de `PodMemberRequiredMixin`. Nenhuma
delas monta o queryset "cru" (`Model.objects.all()`) — sempre filtra por
`self.pod`.

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
- [`GameParticipant.clean()`](../apps/core/models/game_participant.py)
  valida que jogador e partida pertencem ao mesmo pod (ver seção acima).
- [`Pod.save()`](../apps/pods/models/pod.py) gera o `slug` automaticamente
  a partir do `name` na primeira vez (com sufixo se colidir) — renomear o
  pod depois **não** muda o slug, então URLs continuam estáveis.

Em contraste, `Card` e `GameParticipant` (fora do `clean()` acima) são
intencionalmente modelos de dados simples — não é esquecimento, é porque
não têm mais nenhuma regra a proteger.

## Views são Class-Based e finas

Views não fazem query nem agregação diretamente — elas só resolvem o
pod (via mixin), instanciam o use case e chamam `.execute()`:

```python
class DashboardView(PodMemberRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(DashboardStatsUseCase().execute(self.pod, since=since))
        return context
```

CRUD de dado do jogo (`GameCreateView`, `DeckCreateView`,
`PlayerCreateView`, em [`apps/core/views/`](../apps/core/views/)) usa
`Form`/`ModelForm`/`CreateView` do Django direto — sem use case, porque
não há agregação, só validação + `save()`. O caso mais complexo é
[`GameCreateView`](../apps/core/views/game_create.py): um form pros
dados da partida + um `formset_factory` (não `modelformset_factory`,
porque os `GameParticipant` ainda não existem até o `Game` ser salvo)
pros participantes, com resolução de carta MVP/maior criatura por nome
exato (`Card.objects.filter(name__iexact=...)`) em vez de autocomplete —
ver [`apps/core/forms/game.py`](../apps/core/forms/game.py).

## Use Cases orquestram a regra de negócio

Toda a agregação do dashboard (ranking de jogadores, win rate %,
porcentagem de wincon, MVP) vive em
[`apps/core/use_cases/dashboard_stats.py`](../apps/core/use_cases/dashboard_stats.py),
na classe `DashboardStatsUseCase(BaseUseCase)`, implementando
`perform_request(pod, since=None) -> dict`. É a implementação real da
convenção descrita em [conventions.md](./conventions.md): um pacote
`use_cases/` com um módulo por caso de uso, reexportado em
`use_cases/__init__.py`, do mesmo jeito que `models/` e `views/` já
funcionam — e toda classe herda de
[`apps.core.use_cases.base.BaseUseCase`](../apps/core/use_cases/base.py),
que centraliza o logging de início/sucesso/erro/fim em `execute()`. Ao
adicionar uma tela nova com lógica não trivial, o padrão é esse: escrever
o use case primeiro (herdando de `BaseUseCase`), a view só instancia e
chama `.execute()`.

Use cases que agregam o pod inteiro (`DashboardStatsUseCase`,
`PodInsightsUseCase`) recebem `pod` como primeiro argumento de
`perform_request`. Use cases que operam sobre um objeto já resolvido
(`PlayerProfileUseCase`, `GameDetailUseCase`, `DeckDetailUseCase`)
recebem esse objeto direto — o isolamento por pod já veio de como a view
buscou o objeto (`Player.objects.filter(pod=self.pod)`), não precisa ser
repetido no use case.

`apps/pods/use_cases/` segue o mesmo padrão pro fluxo de entrada num pod:
`CreatePodUseCase` (cria o `Pod`, a `Membership` como `OWNER`, e o
`Player` automático de quem criou) e `JoinPodUseCase` (resgata convite,
cria `Membership` de membro comum + `Player` automático).

## Admin: opcional, não é mais o fluxo principal

O CRUD de partida/deck/jogador roda pelo próprio app agora (ver seção de
Views acima) — o Django Admin deixou de ser necessário no dia a dia e
**vem desativado por padrão**: `config/urls.py` só registra
`admin.site.urls` se a env var `ADMIN_ENABLED` estiver ligada (default
`false`). O código do admin continua existindo, só não fica exposto.

[`apps/core/admin.py`](../apps/core/admin.py) e
[`apps/cards/admin.py`](../apps/cards/admin.py) concentram customizações
que valem a pena reaproveitar caso o admin seja religado:

- `DeckAdminForm` — esconde/desabilita o campo `player` condicionalmente
  quando ele já veio via query param.
- Inlines (`GameParticipantInline`, `AchievementInline`,
  `PlayerProfileInline`) e `formfield_for_foreignkey` sobrescrito pra
  desabilitar o "+" de adicionar `mvp_card` direto do inline.
- `GameAdmin.get_urls()` + `get_player_decks()` — endpoint JSON próprio
  dentro do admin, sem precisar de uma app/API separada.
- `class Media: js = (...)` — como acoplar JS customizado a uma tela do
  admin.
- `CardAdmin` ([`apps/cards/admin.py`](../apps/cards/admin.py)) como
  somente-leitura (`has_add_permission`, `has_change_permission`,
  `has_delete_permission` retornando `False`) — cartas só devem ser
  criadas/atualizadas via `import_mtgjson`.
- `DeckAdmin.get_fields` / `get_changeform_initial_data` / `save_model` —
  como prefixar um campo a partir de um query param (usado no fluxo de
  "criar deck a partir da tela do jogador" — o mesmo truque existe na
  versão não-admin em
  [`DeckCreateView.get_initial()`](../apps/core/views/deck_create.py)).

## Login: django-allauth

`django.contrib.auth` + `django-allauth` (`allauth.account` pra
email/senha, `allauth.socialaccount` + provider `google` pra login
social). Credenciais do Google vêm de env
(`GOOGLE_CLIENT_ID`/`GOOGLE_CLIENT_SECRET`) direto em
`SOCIALACCOUNT_PROVIDERS["google"]["APP"]` — sem depender de um registro
`SocialApp` no banco, consistente com o padrão de configuração via
`.env` do resto do projeto.

Templates próprios em `templates/account/` (`login.html`, `signup.html`,
`logout.html`) sobrescrevem os padrões do allauth pra usar o mesmo design
system (Tailwind CDN, estilo Cal.com) do resto do site.

`apps/pods/context_processors.py:user_pods` injeta a lista de pods do
usuário logado em todo template (usado pelo seletor de pod na navbar em
`templates/base.html`).

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
  namespace `apps` (cobre `apps.core.*`/`apps.cards.*`/`apps.pods.*` por
  herança do próprio módulo `logging`) e um logger `django` — ambos com
  nível configurável via env (`APP_LOG_LEVEL`, `DJANGO_LOG_LEVEL`). Uso
  de referência em
  [`import_mtgjson.py`](../apps/cards/management/commands/import_mtgjson.py).
- Hardening de produção em `production.py`: `ALLOWED_HOSTS` vem do env,
  `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` e `SECURE_SSL_REDIRECT`
  ligados (assume produção atrás de HTTPS). `local.py` não tem esse
  hardening — dev roda em HTTP puro.
