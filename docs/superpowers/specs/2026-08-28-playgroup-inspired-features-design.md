# Comandometro — Melhorias Inspiradas no Playgroup.gg

**Data:** 2026-08-28
**Status:** Aprovado para virar plano de implementação

## Contexto

Pesquisei o [playgroup.gg](https://playgroup.gg), um tracker de EDH freemium,
pra achar ideias de métricas/UX que nosso pod fechado poderia usar. O site
tem duas frentes: um contador de vida ao vivo (multiplayer em tempo real,
usado NA mesa) e uma base global de estatísticas por comandante (ELO,
win-rate por posição na mesa, matchups, "salt meter", nota de diversão,
staples que aumentam win rate, etc.), construída a partir de 665 mil+
partidas de todos os usuários.

Depois de discutir a lista completa de ideias, o usuário decidiu **adiar**
seis itens que exigem mudança de arquitetura ou de granularidade de dado
(contador de vida ao vivo, pontuação customizável estilo Playscore, staples
que ganham partida — que exigiria trackear decklist completa —, mulligans
por jogador, duração de turno, e ELO) e aprovou implementar agora os nove
itens que são extensão direta do que já existe: hero banner de comandante,
janela de tempo no dashboard, gráfico de tendência no perfil, win rate por
posição inicial na mesa, salt meter, nota de diversão, wincon breakdown por
deck, confronto direto entre comandantes, e arqui-inimigo de um deck.

## 1. Nova tela: Detalhe do Deck (`/decks/<id>/`)

Quatro dos nove itens aprovados são, na prática, seções de uma mesma tela
nova — o "hero" de um deck específico (não um comandante abstrato global:
como não temos decklist completa nem um conceito de "comandante" separado
de "deck de um jogador", a página é sobre a instância `Deck`, do mesmo jeito
que `commander_stats` no perfil do jogador já é por deck, não por nome de
comandante).

- **Hero banner**: arte do(s) comandante(s) do deck como fundo, nome, e win
  rate em destaque (games/vitórias), espelhando o estilo da página de
  comandante do Playgroup.gg, mas usando nosso design system atual (Tailwind
  CDN, tema claro "Cal.com style" já estabelecido) — sem trocar de
  biblioteca de UI nem de paleta.
- **Wincon breakdown do deck**: mesmo cálculo que já existe pro pod inteiro
  (`PodInsightsUseCase`), agora filtrado pra esse deck.
- **Matchups**: para cada comandante adversário que já jogou contra esse
  deck, quantas partidas, e o win rate desse deck contra ele.
- **Arqui-inimigo**: não é um cálculo novo — é só a primeira linha da lista
  de matchups (o adversário com pior win rate contra esse deck).
- **Partidas recentes**: lista das últimas partidas desse deck, linkando
  pro detalhe da partida.

`Deck` ganha um `get_absolute_url()`-like link a partir de:
`DeckAdmin`/dashboard "Top Comandantes"/perfil do jogador "Comandantes
Pilotados" — todos passam a apontar pra essa tela nova.

## 2. Campos novos em `GameParticipant`

Três campos opcionais, seguindo exatamente o padrão dos que já existem
(`board_wipes_count`, `is_self_elimination`, etc. — nada obrigatório, sem
pressão pra preencher toda partida):

- `starting_seat` (`PositiveSmallIntegerField`, `null=True`, `blank=True`) —
  posição inicial na mesa (1 = primeiro a jogar). Base pra "quem começa
  jogando ganha mais?".
- `felt_salty` (`BooleanField`, `default=False`) — marcado num participante
  que **não** venceu a partida, indicando que achou a vitória do adversário
  irritante/"salgada". Vira o "salt meter" por deck: quando esse deck
  vence, em quantos % das vezes alguém na mesa marcou `felt_salty=True`.
- `fun_rating` (`PositiveSmallIntegerField`, `null=True`, `blank=True`,
  validado entre 1 e 5) — nota de diversão daquele jogador pra aquela
  partida especificamente (não do deck em geral).

## 3. Janela de tempo no dashboard

Em vez de duplicar cada seção em "sempre / semana / mês" (o que infla o
dashboard exatamente do jeito que já cortamos há pouco), um filtro único
via query param (`?days=7`, `?days=30`, ausente = sempre) que afeta os
números do topo (maior vencedor, maior wincon, ranking, ranking de
pontuação) — três botões simples no topo da página. `DashboardStatsUseCase`
e `PodInsightsUseCase` ganham um parâmetro opcional `since` (data) que,
quando presente, filtra os `Game` considerados.

## 4. Gráfico de tendência no perfil do jogador

Sem adicionar biblioteca de gráfico nova (mantendo a mesma decisão de
"sem dependência JS extra" que já seguimos no resto do projeto): um
sparkline em **SVG puro, gerado no servidor** — win rate mês a mês do
jogador, como uma linha simples. `PlayerProfileUseCase` calcula os pontos
(mês, win rate), e um pequeno helper monta o `<polyline>` do SVG — nenhuma
lib de gráfico, nenhum JS de renderização no cliente.

## 5. Novos cálculos (reaproveitando o que já existe)

- **Win rate por posição inicial na mesa**: nova seção colapsável no
  dashboard (mesmo padrão `<details>` já usado pra "Win Rate por Cor" etc.),
  agregando `starting_seat` de todos os `GameParticipant`.
- **Matchups / arqui-inimigo**: método novo, usado tanto no Detalhe do Deck
  quanto (opcionalmente) resumido nos "Recordes do Pod" do dashboard
  ("comandante mais temido" = arqui-inimigo mais comum entre todos os
  decks).
- **Salt meter e nota de diversão**: aparecem no Detalhe do Deck (média do
  deck) e como destaques nos "Recordes do Pod" existentes (deck mais
  "salgado", deck mais divertido) — reaproveitando o mesmo padrão de
  `top_by()` já usado pros recordes de board wipes/counterspells/etc.

## Organização dos arquivos

Segue a mesma convenção já usada (um use case por responsabilidade, uma
view por tela):

```
apps/core/use_cases/
├── deck_detail.py     (novo — DeckDetailUseCase: hero stats, wincon
│                        breakdown, matchups, partidas recentes)
├── dashboard_stats.py  (ganha parâmetro `since` opcional)
├── pod_insights.py     (ganha parâmetro `since`; recordes ganham salt/fun)
└── player_profile.py   (ganha os pontos do sparkline de tendência)

apps/core/views/
└── deck_detail.py      (novo — DeckDetailView)

apps/core/templates/core/
└── deck_detail.html    (novo)
```

## Fora de escopo (adiado, não faz parte deste plano)

Contador de vida ao vivo, pontuação customizável estilo Playscore, análise
de staples por carta (exige decklist completa), mulligans por jogador,
duração de turno, e rating ELO. Ficam registrados aqui como ideias futuras
já pesquisadas, caso o pod queira retomar depois.
