# Comandometro — Multi-tenant: Pods, Login e CRUD sem Admin

**Data:** 2026-08-29
**Status:** Aprovado para virar plano de implementação

## Contexto

O Comandometro hoje serve um único pod global, sem login: qualquer pessoa
com acesso ao site vê os mesmos dados, e todo cadastro (partida, deck,
jogador) passa pelo Django Admin. Isso não escala pro objetivo real: a
mesma pessoa pode ter mais de um playgroup (ex: um pod de amigos e outro
do trabalho), e hoje isso exigiria copiar o projeto inteiro por pod — o
mesmo problema que a planilha original tinha e que o Comandometro nasceu
pra resolver.

Este documento cobre, como um projeto único (as quatro frentes são
interdependentes — não dá pra ter pod sem login, nem CRUD sem permissão
de pod):

1. Login (email/senha padrão + login social, começando por Google) via
   `django-allauth`.
2. Conceito de **Pod**: um usuário pode criar/participar de vários,
   cada um com seus próprios jogadores, decks, partidas e dashboard —
   totalmente isolados entre si.
3. Convite estilo Discord: link único por pod, regenerável.
4. CRUD de partida/deck/jogador **sem depender do Admin** — qualquer
   membro do pod cadastra.

Como consequência, o Admin do Django deixa de ser necessário no dia a dia
e é desativado por padrão (mas não removido — pode ser religado via env
var se algum dia for preciso).

Os 5 jogos e os jogadores/decks já importados em produção (ver
`import_last_5_games.py`, sessão anterior) serão **descartados**, não
migrados — não valem o custo de uma migração de dados só pra manter um
teste pontual.

## 1. Estrutura de apps

```
apps/cards/    Card (catálogo MTG global, ~35k cartas) + import_mtgjson
apps/pods/     Pod, Membership, convite, mixins de permissão, glue com allauth
apps/core/     Player, Deck, Game, GameParticipant, Achievement,
               dashboard/use_cases/views (tudo agora escopado por pod)
```

`apps/shared` deixa de existir — `BaseUseCase` vira
`apps/core/use_cases/base.py`. `Card` sai do `core` para `apps/cards`
porque é dado de referência global, igual pra todo mundo, nunca filtrado
por pod — mantê-lo junto de `Player`/`Deck`/`Game` misturaria dado
"do sistema" com dado "de um pod específico" no mesmo app.

`import_mtgjson.py` migra para `apps/cards/management/commands/` junto
com o model. `seed_games.py` (dev-only) é reavaliado na fase de
implementação — hoje ele cria dados sem pod, então precisa passar a
receber/criar um pod também.

## 2. Modelo de dados

### `apps/pods`

```python
class Pod(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True)  # gerado de `name`, sufixo se colidir
    invite_token = models.UUIDField(default=uuid4, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

class Membership(models.Model):
    class Role(models.TextChoices):
        OWNER = "owner", "Dono"
        MEMBER = "member", "Membro"

    pod = models.ForeignKey(Pod, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER)

    class Meta:
        unique_together = ("pod", "user")
```

Não existe campo `Pod.owner` — o dono é quem tem `Membership.role=OWNER`.
Evita duas fontes de verdade (FK direta vs. role) apontando pra mesma
coisa.

Regenerar o convite = trocar `invite_token` por um `uuid4()` novo
(invalida o link anterior automaticamente, sem precisar de tabela de
convites separada).

### `apps/core` — mudanças nos models existentes

- **`Player`** ganha:
  - `pod = models.ForeignKey("pods.Pod", on_delete=models.CASCADE, related_name="players")` (obrigatório)
  - `user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="players")` (opcional — permite jogador "convidado" sem conta)
  - `unique_together` deixa de ser `name` globalmente único e passa a ser `("pod", "name")`.
- **`Game`** ganha `pod = models.ForeignKey("pods.Pod", on_delete=models.CASCADE, related_name="games")` (obrigatório) — é o único outro model com FK direta de pod, porque não tem nenhum FK obrigatório (deck/player) de onde derivar isso.
- **`Deck`, `GameParticipant`, `Achievement`**: **sem campo `pod` próprio.** O pod já é alcançável via relação existente (`Deck.player.pod`, `GameParticipant.player.pod` / `GameParticipant.game.pod`, `Achievement.player.pod`). Adicionar `pod` nessas tabelas seria denormalização sem necessidade real — o projeto já tem uma postura explícita contra over-engineering (`.docs/conventions.md`).
- **Validação nova em `GameParticipant.clean()`**: garante `self.player.pod_id == self.game.pod_id` — impede vincular um jogador de um pod a uma partida de outro.

### Onboarding automático de `Player`

Ao entrar num pod (seja criando, seja resgatando um convite), o sistema
cria automaticamente um `Player` vinculado ao novo `Membership`
(`user` preenchido, `name` pré-preenchido com o nome da conta Google ou a
parte antes do `@` do e-mail — editável depois). Jogadores avulsos sem
conta continuam possíveis: qualquer membro cadastra um `Player` manual
com `user=None`.

## 3. Dados de produção existentes

Descartados, não migrados. A migration que adiciona `Player.pod` e
`Game.pod` como campos obrigatórios começa com um `RunPython` que apaga
todas as linhas de `Achievement`, `GameParticipant`, `Deck`, `Player` e
`Game` (nessa ordem, respeitando FKs) **antes** de alterar o schema —
evita o dance nullable → backfill → not-null, já que não há nada a
preservar. `Card` (catálogo MTG) não é tocado. Isso roda sozinho no
próximo deploy, dentro do `migrate` que o `build.sh` já executa.

## 4. Autenticação

- **`django-allauth`**, com `allauth.account` (email/senha) e
  `allauth.socialaccount` (Google como primeiro provider). Outros
  providers (Facebook, Apple) são só questão de adicionar a entrada em
  `SOCIALACCOUNT_PROVIDERS`, sem mudança estrutural.
- Credenciais do provider Google via env (`GOOGLE_CLIENT_ID`,
  `GOOGLE_CLIENT_SECRET`) direto em `SOCIALACCOUNT_PROVIDERS["google"]["APP"]`
  nas settings — sem depender de linha `SocialApp` cadastrada no banco,
  consistente com o padrão do projeto de configuração via `.env`
  (ver `.docs/best-practices.md`).
- Novas `INSTALLED_APPS`: `django.contrib.sites`, `allauth`,
  `allauth.account`, `allauth.socialaccount`,
  `allauth.socialaccount.providers.google`. Novo middleware:
  `allauth.account.middleware.AccountMiddleware`. `SITE_ID = 1`.
- `LOGIN_URL` e `LOGIN_REDIRECT_URL` apontam pra `/pods/` (lista de pods
  do usuário).
- Templates de login/signup próprios (não os padrão do allauth), seguindo
  o mesmo design system (Tailwind CDN, estilo Cal.com) do resto do site.

## 5. Permissões

- **`PodMemberRequiredMixin`** (`apps/pods/mixins.py`): em `dispatch()`,
  resolve o `Pod` pelo `pod_slug` da URL, exige `request.user`
  autenticado e com `Membership` nesse pod (senão, 404 — não revela que o
  pod existe pra quem não é membro), e expõe `self.pod`. Toda view de
  `apps/core` passa a herdar dele.
- **`PodOwnerRequiredMixin`** (estende o anterior): exige
  `role=OWNER`, usado só nas views de configuração do pod (renomear,
  regenerar convite, remover membro, apagar pod).
- Qualquer membro (dono incluso) pode criar/editar partida, deck e
  jogador — não há distinção de papel pra isso, só pras ações
  administrativas do próprio pod.

## 6. Django Admin

Desativado por padrão: `config/urls.py` só inclui
`path(settings.ADMIN_URL, admin.site.urls)` se uma env var nova
(`ADMIN_ENABLED`, default `false`) estiver ligada.
`django.contrib.admin` continua em `INSTALLED_APPS` e todo o código do
admin (`apps/core/admin.py`, etc.) continua existindo — religar no futuro
é só ativar a env var no Render, sem mudança de código nem novo deploy de
código (só de config).

## 7. URLs

```
/accounts/...                         allauth: login, signup, logout, Google
/pods/                                 lista dos seus pods + criar + entrar via link
/pods/novo/                            criar pod (você vira OWNER automaticamente)
/pods/entrar/<uuid:token>/             resgatar convite (pede login antes, se preciso)

/p/<slug:pod_slug>/                              dashboard (era "/")
/p/<slug:pod_slug>/jogadores/                    lista de jogadores
/p/<slug:pod_slug>/jogadores/novo/               NOVO — cadastrar jogador (com ou sem conta)
/p/<slug:pod_slug>/jogadores/<int:pk>/           perfil do jogador
/p/<slug:pod_slug>/partidas/                     lista de partidas
/p/<slug:pod_slug>/partidas/nova/                NOVO — cadastrar partida (form + formset de participantes)
/p/<slug:pod_slug>/partidas/<int:pk>/            detalhe da partida
/p/<slug:pod_slug>/decks/novo/                   NOVO — cadastrar deck
/p/<slug:pod_slug>/decks/<int:pk>/               detalhe do deck
/p/<slug:pod_slug>/config/                       NOVO — só dono: renomear, regenerar convite, remover membro, apagar pod
```

`config/urls.py` passa a ter `apps.pods.urls` (namespace `pods`, sem
prefixo de pod) e `apps.core.urls` (namespace `core`, agora incluído sob
`p/<slug:pod_slug>/`).

## 8. Telas e layout

- Navbar (`templates/base.html`) ganha: seletor de pod (dropdown, só
  aparece se o usuário estiver em mais de um pod), nome/avatar do usuário
  e logout. O link do logo/marca volta pra `/pods/` em vez do dashboard.
- Tela `/pods/` nova: cards simples, um por pod, com nome e atalho de
  entrar; botão "Criar pod" e campo "Colar link de convite".
- Formulário de nova partida é a peça mais complexa: um form pra dados da
  partida (data, wincon, notas, contagem de turnos) + um formset dinâmico
  de participantes (jogador do roster do pod, deck, colocação, kills,
  MVP, etc. — os mesmos campos que hoje só existem no inline do Admin).
  Resto do design system (Tailwind CDN, tipografia, paleta) permanece
  igual.

## Fora de escopo

Testes automatizados (mantém o risco assumido explicitamente pelo
usuário), múltiplos links de convite com expiração/limite de uso,
transferência de dono, exclusão de conta, providers de login além de
Google no primeiro momento (mas a estrutura do allauth já deixa isso
plugável sem retrabalho).
