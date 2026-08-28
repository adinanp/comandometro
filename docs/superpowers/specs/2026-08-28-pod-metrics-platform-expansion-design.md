# Comandometro — Novas Métricas, Novas Telas, Admin Oculto e Imagens do Scryfall

**Data:** 2026-08-28
**Status:** Aprovado para virar plano de implementação

## Contexto

O Comandometro nasceu de uma planilha do Google Sheets que o pod já usava
pra acompanhar partidas de Commander/EDH. Comparamos o dashboard atual com
o que a planilha tem hoje e encontramos:

**Já coberto (mesma granularidade):** total de partidas, vitórias por
comandante/jogador, win rate %, breakdown de wincon + %, kill count por
participante, carta MVP por partida, top comandantes/metagame share,
achievements em texto livre, e decks por jogador (dado já existe no
modelo, só não tem tela dedicada).

**Visualizações que a planilha tem e o sistema não:**
1. Win rate por cor individual (mono W/U/B/R/G)
2. Win rate por número de cores no deck (1c/2c/3c/4c/5c)
3. Leaderboard "top comandantes" filtrado (≥5 jogos, ≥20% de vitórias)
4. Evolução do wincon mais usado mês a mês (tendência no tempo)
5. Pontuação estilo F1 (4/2/1/0 pontos por 1º/2º/3º/4º lugar) como ranking
   alternativo ao contador simples de vitórias
6. Abas **vazias mas nomeadas** na planilha (`player_profiles`,
   `top_commanders_appearences`, `most_wincon`, `combeiros`, `tryhards`) —
   validam a ideia de uma tela de perfil de jogador e sugerem outras
   métricas "for fun" que nunca saíram do papel

**Métricas pedidas que não existem em lugar nenhum** (nem na planilha, nem
no sistema — são inéditas): maior criatura (sem combo), jogo mais rápido
(sem/com combo), mais vida em uma partida (sem combo), mais chorão
(reclamações numa partida), maior número de board wipes, counterspells, e
suicídios (morte causada por si mesmo).

Junto com isso, o pod quer evoluir a plataforma além do dashboard único
(perfil de jogador, detalhe de partida), esconder o admin do Django do
restante do site, e mostrar a arte das cartas (comandantes e MVP) usando
o `scryfall_id` que já vem disponível via MTGJSON.

Este documento cobre as quatro frentes como um design único, por decisão
explícita do usuário (o escopo é grande o bastante pra normalmente
justificar specs separados, mas foi decidido tratar como um projeto só).

## 1. Novas métricas — modelagem de domínio

As 7 métricas pedidas são fatos por **participante em uma partida**,
exceto "jogo mais rápido" (que é da partida como um todo, não de um
jogador específico). Modelamos como campos estruturados em `Game` e
`GameParticipant` — não como texto livre em `Achievement` — porque essas
métricas devem ser rankeáveis e comparáveis (ex: "quem tem mais board
wipes na carreira"), não só registradas como um troféu único.

### `Game` ganha um campo novo

- `turn_count` (`PositiveIntegerField`, `null=True`, `blank=True`) — nº de
  turnos da partida. Base para "jogo mais rápido"; o filtro "sem/com
  combo" é só um `.filter(win_condition="combo")` / `.exclude(...)` em
  cima do `win_condition` que já existe, sem campo novo.

### `GameParticipant` ganha seis campos novos

- `peak_life_total` (`IntegerField`, `null=True`, `blank=True`) — vida
  mais alta atingida pelo participante na partida. Base para "mais vida
  em uma partida".
- `board_wipes_count` (`PositiveIntegerField`, `default=0`) — quantas
  vezes o participante resetou o board na partida.
- `counterspell_count` (`PositiveIntegerField`, `default=0`) — quantos
  counterspells o participante resolveu na partida.
- `complaint_count` (`PositiveIntegerField`, `default=0`) — "mais
  chorão": quantas vezes o participante reclamou durante a partida.
- `is_self_elimination` (`BooleanField`, `default=False`) — "suicídio":
  o participante foi eliminado por uma ação própria, não por outro
  jogador. Boolean simples em vez de um enum de "causa de eliminação" —
  é a única distinção que o pod pediu, um enum seria over-engineering
  pra esse caso.
- `biggest_creature` (`ForeignKey` para `Card`, `null=True`,
  `blank=True`) + `biggest_creature_power` (`PositiveIntegerField`,
  `null=True`, `blank=True`) — a maior criatura que bateu na mesa nessa
  partida. Guardamos o **poder alcançado naquela partida**, não um poder
  "oficial" da carta, porque bônus e equipamentos mudam esse valor
  partida a partida — não existe (e não deveria existir) um campo fixo
  de poder em `Card` pra derivar isso.

Todos os campos são opcionais ou têm `default=0` — nenhum jogador é
obrigado a preencher os 6 campos novos em toda partida. Ninguém quer
digitar 9 campos por participante toda vez que registra uma partida no
admin.

### Recordes deixam de ser curados à mão

Os "recordes" (maior board wipe, jogo mais rápido, etc.) não viram
entradas manuais em `Achievement` como o `EPIC_ACHIEVEMENTS` de hoje —
viram **queries agregadas ao vivo** (`MAX()`/`annotate()` sobre os campos
acima), sempre atualizadas sozinhas conforme novas partidas entram.
`Achievement` continua existindo exatamente como está hoje, para os
feitos históricos e orgânicos que o pod já registrou (Torment of
Hailfire, etc.) — não faz sentido migrar esses dados nem duplicar o
padrão para as métricas novas.

### Migração

Uma migração nova adiciona os 7 campos (`Game.turn_count` +
os 6 em `GameParticipant`). Sem backfill — dados históricos ficam com
esses campos `null`/`0`, e os recordes computados simplesmente ignoram
partidas sem o dado (uma partida com `board_wipes_count=0` não é
candidata a "recorde de board wipes", é indistinguível de "não
preencheu" — isso é uma limitação aceita, não um bug: não dá pra saber
retroativamente quantos board wipes rolaram numa partida de 2022).

## 2. Novas telas

Hoje existe uma única tela (`DashboardView`). Este design adiciona três:

### Perfil do jogador — `/players/<id>/`

- Recorde geral: jogos, vitórias, win rate, pontuação estilo F1 (ver
  seção 5).
- Decks/comandantes pilotados, com stats por comandante (jogos, vitórias,
  win rate) — o mesmo dado que a aba "commanders by player" da planilha
  já calculava manualmente.
- Recordes pessoais entre as 7 métricas novas (ex: "seu recorde de board
  wipes numa partida: 4").
- Nomes de jogador em qualquer tela (dashboard, ranking, tabela de
  achievements) passam a linkar para o perfil correspondente.

### Detalhe da partida — `/games/<id>/`

- Data, modo de vitória, carta MVP (com imagem — ver seção 4), turn
  count.
- Tabela com cada participante: jogador (linkando pro perfil), deck/
  comandante (com imagem), colocação, kills, board wipes, counterspells,
  reclamações, vida de pico, flag de suicídio.

### Lista de partidas — `/games/`

- Paginada, mais recente primeiro. É a porta de entrada para chegar em
  qualquer detalhe de partida — sem essa tela, `/games/<id>/` só seria
  alcançável por um link específico vindo do perfil de um jogador, o que
  deixaria a maioria das partidas órfãs de navegação.

### Navegação

A navbar (`templates/base.html`) passa a ter `Dashboard | Partidas` — sem
nenhum link de Admin (ver seção 3).

## 3. Segurança do admin

- Nova variável de ambiente `ADMIN_URL`, seguindo o mesmo padrão já usado
  para `SECRET_KEY`/`ALLOWED_HOSTS` (`django-environ`, lida em
  `config/settings/base.py`, documentada em `.env.example`).
- `config/urls.py` monta a rota do admin a partir dessa variável:
  `path(env("ADMIN_URL"), admin.site.urls)` em vez do `admin/` fixo.
  Um default obscuro (gerado por nós, não um valor óbvio como
  `admin-panel/`) cobre o caso de a variável não estar setada — o
  usuário decidiu deixar essa escolha por nossa conta.
- Remove o `<a href="/admin/">Admin</a>` de `templates/base.html` — o
  requisito explícito é que **nenhuma rota do site público aponte para o
  admin**, escondido ou não.
- Checagem final: `grep -rn "/admin/"` no projeto inteiro (fora de
  `config/urls.py`) deve voltar vazio antes de considerar essa frente
  concluída.

## 4. Imagens do Scryfall

- `Card` ganha dois campos: `scryfall_id` (`CharField`, `null=True`,
  `blank=True`) — capturado em `import_mtgjson.py`, que já tem acesso a
  esse dado via `identifiers.scryfallId` no payload do MTGJSON — e
  `image_url` (`URLField`, `null=True`, `blank=True`) — cache da URL da
  imagem, populado sob demanda.
- Um use case novo, `EnsureCardImageUseCase` (herdando de
  `BaseUseCase`, em `apps/core/use_cases/card_image.py`), busca a imagem
  na API pública do Scryfall (`GET https://api.scryfall.com/cards/
  {scryfall_id}`, extraindo `image_uris.normal` — ou
  `card_faces[0].image_uris.normal` pra cartas de dupla face) **apenas
  quando uma tela precisa exibir aquela carta especificamente**
  (comandante de um deck, ou carta MVP de uma partida). Isso evita baixar
  dado de imagem para as ~30 mil cartas que o `import_mtgjson` traz do
  MTGJSON, das quais só uma fração pequena (comandantes usados, MVPs
  votados) chega a aparecer numa tela.
- Guardamos só a **URL** da imagem (hotlink direto no CDN do Scryfall),
  não o binário — as guidelines do Scryfall permitem esse uso
  explicitamente, e isso evita custo de storage e infraestrutura de mídia
  que o projeto não precisa.
- Resiliência: se a busca falhar (rate limit, carta sem `scryfall_id`,
  API fora do ar), o use case loga o erro e retorna `None` em vez de
  deixar a exceção derrubar a página — internamente,
  `perform_request()` tem seu próprio `try/except` ao redor da chamada
  HTTP (diferente de deixar o `try/except` do `BaseUseCase.execute()`
  relançar), porque uma imagem faltando não é uma falha do use case, é um
  resultado válido esperado.
- Views que precisam mostrar cartas (dashboard, perfil do jogador,
  detalhe da partida) chamam `EnsureCardImageUseCase().execute(card)`
  para cada carta relevante ao montar o contexto — os templates só
  recebem uma URL (ou `None`) já resolvida, nunca fazem chamada de rede.

## 5. Dashboard enriquecido com achados da planilha

Tudo nesta seção usa dados que **já existem** hoje — sem migração nova.
Vira um use case novo, `PodInsightsUseCase` (`apps/core/use_cases/
pod_insights.py`), separado do `DashboardStatsUseCase` existente para não
inflar ainda mais um arquivo que já tem uma responsabilidade clara.

- Win rate por cor individual (W/U/B/R/G) e por número de cores no deck
  (mono/2c/3c/4c/5c) — derivado de `Deck.color_identity`.
- Evolução do wincon mais usado mês a mês — agrupando `Game.date` por mês
  (gráfico de tendência, algo que hoje só existe como total acumulado).
- Ranking "top comandantes" filtrado (≥5 jogos, ≥20% de vitórias) —
  variação qualificada do ranking que já existe.
- Pontuação estilo F1 (4 pontos por 1º lugar, 2 por 2º, 1 por 3º, 0 pelo
  resto) como ranking alternativo ao contador de vitórias puro — usado
  tanto no dashboard quanto no perfil do jogador.
- Os recordes das 7 métricas novas (seção 1) também são computados aqui,
  para exibição em uma nova seção "Recordes" no dashboard.

## Organização dos arquivos

Segue a convenção já estabelecida (pacote de arquivos, um módulo por
caso de uso/view, reexportado em `__init__.py`):

```
apps/core/use_cases/
├── dashboard_stats.py    (existente, sem mudança de escopo)
├── pod_insights.py        (novo — cores, tendência, F1, top filtrado, recordes)
├── player_profile.py      (novo)
├── game_detail.py         (novo)
└── card_image.py          (novo — EnsureCardImageUseCase)

apps/core/views/
├── dashboard.py            (existente, passa a chamar 2 use cases)
├── player_profile.py       (novo)
├── game_list.py            (novo)
└── game_detail.py          (novo)

apps/core/templates/core/
├── dashboard.html           (existente, seções novas)
├── player_profile.html      (novo)
├── game_list.html           (novo)
└── game_detail.html         (novo)
```

## Fora de escopo

- Testes automatizados continuam fora de escopo (decisão já tomada em
  conversa anterior).
- Download/armazenamento local de imagens do Scryfall (hotlink de URL é
  suficiente, ver seção 4).
- Migração dos `Achievement` existentes para o novo modelo estruturado.
- As demais abas vazias da planilha (`most_wincon`, `combeiros`,
  `tryhards`, `top_commanders_appearences`) além do que já foi
  incorporado nas seções 2 e 5 — ficam registradas aqui como ideias
  futuras, não como parte deste plano.
