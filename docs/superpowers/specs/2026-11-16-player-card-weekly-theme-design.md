# Card do Jogador + Tema da Semana — Design

> Status: brainstorm de 2026-11-16. **Depende do PR #1** (sorteio de temas:
> `Theme`, `sync_edhrec_themes`, `EnsureThemeSummaryUseCase`, `week_start`),
> branch `claude/theme-draw-brainstorm-314850` — esta branch parte dela.

## Intenção

Na home de cada pod (dashboard), o jogador logado ganha um card na lateral
direita que:

1. mostra a **performance individual** dele naquele pod; e
2. funciona como **gatilho de desafio para sair da zona de conforto**: mostra
   onde ele já está confortável (o deck que mais joga) e, logo abaixo, um
   **Tema da Semana** pessoal, sorteado para fugir dos temas que ele já joga,
   que pode ser trocado até 2 vezes por semana com um botão ⟳.

## Objetivos

- Card "Você no pod" visível só para o próprio jogador, em todo dashboard de
  pod.
- Bloco de performance: partidas e win rate, pontos e posição no ranking,
  sequência atual, first bloods.
- Bloco "Zona de conforto": deck mais jogado + % das partidas, combinação de
  cores favorita, wincon favorita.
- Bloco "Tema da Semana": arte, nome, nº de decks, top 3 comandantes, resumo
  pt-BR — o mesmo card de tema do sorteio em grupo — e o botão ⟳ com o número
  de trocas restantes.
- Sorteio do tema evitando a zona de conforto do jogador e temas recentes dele.

## Não-objetivos

- Ligar o tema pessoal ao sorteio em grupo (decidido: são **independentes**;
  a mesma pessoa pode ter um tema pessoal e outro numa noite temática).
- Registrar se o jogador "cumpriu" o tema, ou win rate jogando o tema.
- Ver o tema da semana dos outros jogadores.
- Métricas que exigem dados novos (quem eliminou quem, histórico de vida).
- Histórico de temas anteriores na tela (o dado fica guardado, a tela não).
- Seguir o filtro 7/30 dias do dashboard (o card é sempre o histórico todo).

## Anti-objetivos

- O botão ⟳ não pode virar um jeito de **escolher** o tema: uma troca nunca
  volta a um tema já sorteado para a pessoa na semana.
- O dashboard não pode chamar o EDHREC nem esperar a LLM.
- Salvar um deck nunca pode falhar por causa do EDHREC.
- O card não pode quebrar o dashboard de quem não tem jogador no pod, não tem
  partidas ou não tem decks.

## Abordagens consideradas (armazenamento do tema da semana)

1. **Uma linha por tema sorteado — escolhida.** `PlayerWeeklyTheme(player,
   theme, week_start, created_at)`. Tema atual = linha mais recente da semana;
   trocas usadas = linhas da semana − 1. As regras de "não repetir" viram
   consultas diretas e o histórico fica guardado.
2. Uma linha por semana com contador e lista JSON de temas vistos: menos
   linhas, mas perde o histórico e a regra de não repetir vive num JSON.
3. Reusar `ThemeDraw`/`ThemeDrawSeat` com um sorteio de um assento só:
   descartada — a regra semanal do sorteio em grupo passaria a contar temas
   pessoais, e a página/recap do sorteio não fazem sentido para uma pessoa.

Relação com o sorteio em grupo: escolhida a opção "tema pessoal separado"
(entre separado / mesmo dado / sorteio em grupo usa o pessoal).

## Dados

### `apps/cards` — temas de cada comandante (zona de conforto)

Verificado em 2026-11-16: `https://json.edhrec.com/pages/commanders/<slug>.json`
traz `panels.taglinks`, lista ordenada `[{"slug", "value", "count"}]` cujos
`slug` batem com `Theme.slug` (ex.: Atraxa → infect, plus-1-plus-1-counters,
planeswalkers, proliferate, …).

Campos novos em `Card`:

| campo | tipo | nota |
|---|---|---|
| `edhrec_theme_slugs` | JSONField(default=list) | top 5 `taglinks[].slug` do comandante |
| `edhrec_themes_synced_at` | DateTimeField(null) | |

`EdhrecThemeClient` ganha `commander_theme_slugs(card_name, limit=5) -> list[str]`.
Slug do comandante no EDHREC: nome em minúsculas, sem acentos (normalização
Unicode), sem apóstrofos/vírgulas, demais não alfanuméricos → `-`, hífens
colapsados (ex.: "Atraxa, Praetors' Voice" → `atraxa-praetors-voice`). Cartas
com " // " (dupla face) usam só a primeira face. Página inexistente (404) →
lista vazia, sem erro.

**Quando os temas do comandante são buscados** (decidido: buscar ao criar o
deck, para a zona de conforto não ficar atrasada para quem monta deck novo):

- **Ao salvar um deck** (`DeckCreateView`, `DeckCreateAjaxView` e qualquer
  outro fluxo que crie/edite os comandantes de um deck): para cada comandante
  com `edhrec_themes_synced_at` vazio, busca os temas no EDHREC com timeout
  curto (~3 s por carta). Falha ou timeout → deck salvo normalmente, carta fica
  sem dados (a sync manual preenche depois). Implementar num use case
  (`EnsureCommanderThemesUseCase(cards)`) chamado pela view **depois** do
  `save()` — nunca dentro da transação nem num signal que possa derrubar o
  save. Abrir a tela ou o dashboard nunca chama o EDHREC.
- **Na sync manual**: `sync_edhrec_themes` ganha uma etapa final que busca os
  comandantes de `Deck` (qualquer pod — dado global) com
  `edhrec_themes_synced_at` vazio; com `--refresh-commanders`, busca todos de
  novo. Mesma cadência (~5 req/s) e mesma regra de falha (loga, segue).
  `edhrec_themes_synced_at` é preenchido também quando o EDHREC devolve 404
  (lista vazia), para não buscar de novo a cada deck.

### `apps/core` — `PlayerWeeklyTheme`

| campo | tipo | nota |
|---|---|---|
| `player` | FK `Player` (CASCADE, related `weekly_themes`) | o pod vem de `player.pod` |
| `theme` | FK `cards.Theme` (PROTECT) | |
| `week_start` | DateField | segunda-feira da semana (America/Sao_Paulo) |
| `created_at` | DateTimeField(auto_now_add) | ordena dentro da semana |

`Meta.ordering = ["-created_at"]`; índice em (`player`, `week_start`);
`unique_together` (`player`, `week_start`, `theme`) — reforça "nunca o mesmo
tema duas vezes na semana".

## Regras do Tema da Semana

Constantes: `MAX_REROLLS_PER_WEEK = 2`, `RECENT_WEEKS_EXCLUDED = 4`,
`COMFORT_THEMES_PER_COMMANDER = 5`. Semana = `week_start()` de
`apps/core/use_cases/draw_themes.py` (segunda 00:00 America/Sao_Paulo); a
data salva é `week_start(now).date()`.

**Zona de conforto do jogador** = união de `edhrec_theme_slugs` dos
comandantes de **todos os decks cadastrados por ele no pod** (jogados ou não).

**Temas elegíveis** = todos os `Theme`
− temas da zona de conforto
− temas que o jogador recebeu nas últimas 4 semanas (incluindo a atual).

Se não sobrar nenhum: relaxa primeiro a regra das 4 semanas (mantendo só "não
repetir nesta semana"), depois a zona de conforto. *(minha decisão)*

**Atribuição:** na primeira vez que o dashboard é aberto na semana (GET), se o
jogador não tem linha nesta semana, sorteia e cria uma. Quem não abre o pod na
semana fica sem tema — sem efeito colateral.

**Troca (⟳):** POST. Permitido se `linhas da semana < 1 + MAX_REROLLS_PER_WEEK`.
Sorteia entre os elegíveis (que já excluem os temas desta semana) e cria nova
linha; o tema atual passa a ser o novo. Sem trocas restantes → mensagem e nada
muda. O contador volta a 2 na segunda-feira (nova semana = zero linhas).
Clique duplo não pode gastar duas trocas: a troca roda em transação com
`select_for_update()` na linha do `Player`. *(minha decisão)*

## Métricas do card (`PlayerPodCardUseCase`)

`perform_request(player) -> dict` — sempre o histórico todo do jogador no pod.

| chave | definição |
|---|---|
| `games`, `wins`, `win_rate` | como `PlayerProfileUseCase` (win rate %, 1 casa) |
| `points`, `points_rank` | pontos 4/2/1 por colocação (`POINTS_BY_PLACEMENT`); posição entre os jogadores do pod ordenados por pontos (empate divide a posição — "2º" para ambos) |
| `streak` | `{"kind": "wins"|"winless", "count": n}`: percorre as partidas do jogador da mais recente para a mais antiga (`game.date` desc, depois `game.id` desc); `wins` = vitórias seguidas a partir da mais recente; senão `winless` = partidas desde a última vitória. Sem partidas → `None` |
| `first_bloods` | nº de `Game` com `first_blood_player = player` |
| `comfort_deck` | deck com mais partidas + `share` = partidas dele / partidas do jogador (%); `None` sem partidas |
| `favorite_color_combo`, `favorite_wincon` | reaproveitar a lógica de `PlayerProfileUseCase` (extrair para funções compartilhadas em vez de duplicar) |

Jogador sem partidas: o bloco de performance mostra "Sem partidas ainda"; o
Tema da Semana aparece normalmente.

## Telas

- `DashboardView` (`apps/core/views/dashboard.py`): resolve
  `Player.objects.filter(pod=self.pod, user=request.user).first()`; se existir,
  chama `PlayerPodCardUseCase` e `EnsureWeeklyThemeUseCase` e põe no contexto.
  Sem jogador → sem card.
- Layout (`core/dashboard.html`): no `lg`, duas colunas — conteúdo atual à
  esquerda, card à direita (~320 px, `sticky top`); abaixo de `lg`, o card vem
  **antes** do conteúdo, em largura total. *(minha decisão)*
- Rascunho do card:

```
VOCÊ NO POD
42 partidas · 31% win rate
58 pts · 2º no ranking
Sequência: 3 sem vencer
First bloods: 7

ZONA DE CONFORTO
Atraxa, Praetors' Voice — 61% das suas partidas
Cores: WUBG · Wincon: Combo

TEMA DA SEMANA                     ⟳ 2
[arte] ARISTOCRATS
68,8 mil decks
Teysa Karlov · Sephiroth · Meren
"Sacrifica as próprias criaturas…"
```

- URLs novas (namespace `core`, `PodMemberRequiredMixin`):
  - `meu-tema/trocar/` (POST) → `RerollWeeklyThemeView` → redirect para o
    dashboard (preservando `?days=` se vier). Sem trocas → `messages.error`.
  - `meu-tema/resumo/` (GET) → JSON `{summary}` do tema atual do jogador
    logado, via `EnsureThemeSummaryUseCase` — o card mostra "gerando resumo…"
    e busca por `fetch`, como na página do sorteio.
- Botão ⟳ é um `<form method="post">` (sem JS); desabilitado com "0 trocas"
  quando acabar.

## Use cases novos (`apps/core/use_cases/`)

- `PlayerPodCardUseCase.perform_request(player) -> dict` (métricas acima).
- `EnsureWeeklyThemeUseCase.perform_request(player, now=None) -> dict` —
  garante o tema da semana e devolve `{"theme": Theme, "rerolls_left": int}`.
- `RerollWeeklyThemeUseCase.perform_request(player, now=None) -> dict` — mesmo
  retorno; `ValidationError` sem trocas restantes.
- Função compartilhada `eligible_weekly_themes(player, week) -> QuerySet` com a
  regra de elegibilidade e o relaxamento.

## Testes

- Zona de conforto: tema da lista de um comandante do jogador nunca é sorteado;
  deck sem `edhrec_theme_slugs` não quebra.
- Não repete temas das últimas 4 semanas; relaxa quando acabam os elegíveis.
- Atribuição: primeira visita da semana cria 1 linha; segunda visita não cria.
- Troca: até 2; a 3ª falha sem criar linha; nunca repete tema da semana;
  contador zera na semana seguinte; borda domingo 23:30 / segunda 00:30 SP.
- Métricas: win rate, pontos e posição com empate, sequência (vitórias e
  jejum, ordem por data e id), first bloods, deck de conforto e %.
- Views: card só aparece para quem tem `Player`; não-membro 404 nas URLs novas;
  POST de troca sem trocas mostra mensagem; resumo devolve JSON.
- Sync: slug do comandante (acentos, apóstrofos, dupla face); 404 → lista vazia
  e `synced_at` preenchido; falha num comandante não para a sync; sem
  `--refresh-commanders` só busca quem está sem dados.
- Criar deck: comandante sem dados dispara a busca; com dados, não; EDHREC
  fora do ar → deck criado, sem erro na tela.

## Decisões de borda *(minhas, após revisão)*

- Duas primeiras visitas simultâneas: a atribuição no GET usa o mesmo
  `select_for_update()` na linha do `Player` que a troca, para não criar duas
  linhas (e gastar uma troca sem querer).
- Partidas sem data entram por último na ordem da sequência.
- `sync_edhrec_themes --only <slug>` pula a etapa de comandantes.
- POST de troca sem linha na semana (página aberta no domingo, clique na
  segunda) conta como a atribuição da semana, não como troca.
- Catálogo de temas vazio: o bloco Tema da Semana não aparece; o resto do
  card sim.

## O que fica para o builder

- Estilo visual do card (seguir os cards existentes do dashboard, Tailwind).
- Como extrair os helpers de `PlayerProfileUseCase` sem mudar o comportamento
  da página de perfil.
- Texto exato das mensagens.
