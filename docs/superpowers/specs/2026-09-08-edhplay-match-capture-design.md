# Captura de Partidas do EDHPlay → Comandometro

**Data:** 2026-09-08
**Status:** Aprovado para virar plano de implementação

## Contexto

O pod joga partidas de Commander no [EDHPlay](https://edhplay.com), um
simulador de mesa virtual (React/Vite, roda inteiro no navegador — não é uma
ferramenta de vídeo-chamada tipo SpellTable). Hoje toda partida é lançada no
Comandometro manualmente via [GameForm](../../../apps/core/forms/game.py),
preenchendo à mão os mesmos dados que já estiveram visíveis na tela durante o
jogo (vida, turnos, quem morreu, comandante de cada um).

A ideia: uma extensão de navegador que observa a aba do EDHPlay enquanto uma
pessoa do pod joga e anota a mesa toda, capturando sozinha o que dá pra ler
da tela e oferecendo uma sidebar pra preencher rapidamente o que é subjetivo
— ao final, exporta um `.json` que alimenta uma API nova do Comandometro.

Pesquisa feita durante o brainstorming (ver conversa): o EDHPlay não expõe
estado global em `window` (build de produção minificada) e o modo solo/demo
não faz nenhuma chamada de rede além de assets estáticos — então a captura
tem que ser via leitura do DOM (há um painel "Event Log" nativo com entradas
com timestamp, e vida/turno/zonas aparecem na tela por assento), nunca via
interceptação de tráfego de uma partida real (arriscado e não verificado).

Dois entregáveis, conectados só pelo contrato do JSON:

1. **Extensão de navegador** (repositório novo) — observa o DOM e gera o JSON.
2. **API de import** no Comandometro (`apps/core`) — recebe esse JSON e cria
   `Game` + `GameParticipant`. Chamada manualmente (curl/httpie/Postman) por
   enquanto — a extensão não fala com o Comandometro.

---

## 1. Extensão de navegador

### Escopo de captura

Foi decidido dividir os campos entre **auto-detectado** (visível na tela, lido
via `MutationObserver`) e **manual na sidebar** (subjetivo ou ambíguo):

| Campo | Origem |
|---|---|
| Jogadores na mesa e apelido de cada um | Auto |
| Posição inicial (`starting_seat`) | Auto |
| Comandante de cada deck (nome da carta) | Auto |
| Contagem de turnos (`turn_count`) | Auto |
| Pico de vida por jogador (`peak_life_total`) | Auto |
| Quem foi eliminado, em que turno | Auto |
| Quem eliminou quem | Manual (formulário rápido ao marcar elim.) |
| Vencedor da partida | Manual (confirma/sobrescreve o que a auto-detecção de eliminação sugere) |
| Condição de vitória (`win_condition`) | Manual (texto livre com sugestões) |
| `mvp_card`, `board_wipes_count`, `counterspell_count`, `complaint_count`, `felt_salty`, `fun_rating` | Manual, por jogador |

**Risco a validar cedo (spike):** só foi possível inspecionar o modo
solo/demo do EDHPlay (1 jogador, sem rede). O layout exato do DOM numa mesa
real com 2+ jogadores — como aparecem apelidos, e o estado "eliminado" de um
assento — não foi confirmado. A primeira tarefa da implementação deve ser
abrir uma partida real (com mais alguém, nem que seja duas abas/perfis) só
pra inspecionar o DOM antes de escrever o observer de verdade. Qualquer
detecção automática que não bater com o que foi assumido aqui degrada pra
entrada manual — nunca trava o fluxo de anotar a partida.

### Arquitetura

- **Manifest V3**, só Chrome no v1 (Firefox fica de fora, dá pra portar
  depois).
- **Content script** injetado em `https://edhplay.com/*`, que detecta uma
  partida ativa (presença dos elementos do playmat) e injeta uma **sidebar em
  Shadow DOM** (isola o CSS da extensão do CSS do site).
- Estado da partida em observação vive em memória no content script e é
  persistido incrementalmente em `chrome.storage.local`, pra sobreviver a um
  reload acidental da aba.
- Build com TypeScript + Vite (detalhe a confirmar no plano de
  implementação — não é uma decisão de design).

### Ciclo de vida de uma partida

1. Extensão detecta início de partida (turno vira 1 / "New game started!" no
   Event Log) → mostra prompt discreto "Nova partida detectada — começar a
   registrar?".
2. Durante o jogo, a sidebar atualiza sozinha os campos auto-detectados;
   os manuais podem ser preenchidos a qualquer momento, não só no fim.
   Quando um assento é marcado como eliminado (auto ou manualmente), a
   sidebar pergunta na hora "eliminado por: [outro jogador ▾] / self /
   desconhecido" — constrói a lista de eliminações incrementalmente, em vez
   de pedir tudo de uma vez no fim.
3. Botão "Encerrar partida": confirma vencedor e wincon se ainda faltarem,
   monta o JSON e dispara download via `chrome.downloads`.

### Schema do JSON exportado (v1, versionado)

```json
{
  "schema_version": 1,
  "source": "edhplay",
  "captured_at": "2026-09-08T21:00:00Z",
  "turn_count": 7,
  "win_condition": "Dano de Comandante",
  "notes": "",
  "seats": [
    {
      "seat": 1,
      "display_name": "AdinanP",
      "commander": "Muldrotha, the Gravetide",
      "peak_life_total": 42,
      "eliminated_on_turn": 5,
      "is_winner": false,
      "mvp_card": "Toxic Deluge",
      "board_wipes_count": 1,
      "counterspell_count": 0,
      "complaint_count": 2,
      "felt_salty": true,
      "fun_rating": 4
    }
  ],
  "eliminations": [
    { "victim_seat": 1, "killer_seat": 3, "turn": 5 }
  ]
}
```

Notas sobre o schema:
- `win_condition` e `notes` são do jogo inteiro, não por assento.
- `eliminations` é a lista bruta de quem matou quem — `kill_count` e
  `is_self_elimination` por participante são **derivados** dela (pela API de
  import, ver seção 2), não vão duplicados no JSON. Guardar a lista bruta
  mantém a granularidade pra métricas futuras de "quem mata quem", que não
  estamos construindo agora.
- Nenhum ID do Comandometro aparece aqui — `display_name` e `commander` são
  só o texto como apareceu no EDHPlay. O mapeamento pra `Player`/`Deck` reais
  acontece na chamada da API (seção 2), não na extensão.

### Fora do escopo do v1 (adiado, não esquecido)

- Firefox.
- Parsing de tráfego de rede/WebSocket de uma partida real multiplayer (não
  verificamos que existe, e mexer nisso tem risco de ToS de um site fã-feito).
- Qualquer integração/login da extensão com o Comandometro — decidido que a
  extensão fica desacoplada, só gera o arquivo.
- `biggest_creature`/`biggest_creature_power` (campos existentes em
  `GameParticipant`) — não fazem parte da captura por ora.

---

## 2. API de import no Comandometro

### Endpoint

`POST /pods/<pod_slug>/api/games/import/`, seguindo o padrão de scoping por
pod já usado em `apps/pods` (`PodMemberRequiredMixin`/slug na URL). Sem DRF
no projeto — view simples de Django retornando `JsonResponse`, como o resto
do app já faz.

### Autenticação

Token estático via variável de ambiente (`IMPORT_API_TOKEN`), exigido no
header `Authorization: Bearer <token>`. Sem sessão, sem CSRF, sem modelo
novo no banco — adequado pra uma ferramenta de um usuário só chamando via
curl/httpie. Requisição sem o header ou com token errado → `401`.

### Corpo da requisição

Embrulha o JSON exportado pela extensão com um mapeamento explícito de
assento → `Player`/`Deck`, montado à mão por quem faz a chamada (sem
matching difuso de nome no servidor — evita associação errada silenciosa):

```json
{
  "match": { /* JSON da extensão, schema_version 1, sem alterações */ },
  "seat_mappings": [
    { "seat": 1, "player_id": 5, "deck_id": 12 },
    { "seat": 2, "player_id": 8, "deck_id": null },
    { "seat": 3, "player_id": 3 },
    { "seat": 4, "player_id": 9 }
  ]
}
```

- `player_id` obrigatório para todo `seat` presente em `match.seats`;
  request com algum assento sem mapeamento correspondente → `400`.
- `deck_id` opcional (pode ser omitido ou `null`) — vira
  `GameParticipant.deck = None`, igual ao comportamento já existente no
  `GameForm` pra partidas sem deck definido.
- `player_id`/`deck_id` são validados contra o pod (`Player.pod` /
  `Deck.player.pod`) igual à validação que já existe em
  `GameParticipantForm.clean()` — deck que não pertence ao player mapeado, ou
  player que não pertence ao pod da URL, → `400` com mensagem apontando o
  assento problemático.

### Processamento

Dentro de uma transação (`transaction.atomic`), pra não deixar dado
parcial se algo falhar no meio:

1. Cria `Game`: `pod` (da URL), `date` = data de `match.captured_at`,
   `win_condition = resolve_win_condition(match.win_condition)` (mesma
   função já usada pelo `GameForm`, mantém agrupamento com o histórico
   existente), `turn_count = match.turn_count`, `notes = match.notes`.
2. Para cada `seat` em `match.seats`, usando o `player_id`/`deck_id` do
   mapeamento correspondente, cria um `GameParticipant` com:
   - `player`, `deck` — do mapeamento.
   - `peak_life_total = seat.peak_life_total`.
   - `starting_seat = seat.seat`.
   - `is_winner` não é campo do model — vira `placement` (ver abaixo).
   - `kill_count` = quantas entradas em `match.eliminations` têm
     `killer_seat` igual a este `seat`.
   - `is_self_elimination` = existe alguma entrada em `eliminations` com
     `victim_seat == killer_seat == este seat`.
   - `mvp_card` = resolvido por match exato (case-insensitive) de
     `seat.mvp_card` contra `Card.name`; se não achar nenhuma carta com esse
     nome, fica `None` e a resposta inclui um aviso — **não falha o import
     inteiro** por causa de um nome de carta que não bateu.
   - `board_wipes_count`, `counterspell_count`, `complaint_count`,
     `felt_salty`, `fun_rating` — copiados direto do `seat`.
3. `placement`: o `seat` com `is_winner: true` vira `1`; os demais são
   ordenados por `eliminated_on_turn` decrescente (eliminado mais tarde =
   colocação melhor) e numerados a partir de `2`. Empate de turno de
   eliminação (raro — evento simultâneo) resolvido pela ordem de `seat` como
   critério de desempate estável, sem tentar ser mais esperto que isso.
4. Resposta `201` com `{"game_id": ..., "url": "/pods/<slug>/partidas/<id>/", "warnings": [...]}`
   (warnings = ex. cartas MVP não encontradas). Erro de validação → `400`
   com a lista de problemas encontrados (nunca cria nada parcialmente nesse
   caso, por causa da transação).

### Fora do escopo do v1 (adiado, não esquecido)

- Qualquer UI web de upload/mapeamento — a chamada é manual via HTTP client
  por enquanto.
- Matching automático de nome (`display_name` do EDHPlay → `Player`) — o
  mapeamento é sempre explícito na requisição.
- Auto-criação de `Deck` a partir do texto de `commander` — se `deck_id` não
  vier no mapeamento, o participante fica sem deck, igual ao form manual.
- Qualquer modelo novo para guardar a lista granular de `eliminations` (quem
  matou quem, carta por carta) — só os agregados (`kill_count`,
  `is_self_elimination`) entram no banco por ora; a lista bruta existe no
  JSON pra métricas futuras, não é persistida separada do que já cabe em
  `GameParticipant`.
