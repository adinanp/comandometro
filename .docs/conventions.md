# Convenções de Organização

## Pacote de arquivos, não arquivo solto

Sempre que uma "camada" do projeto cresce o suficiente pra ter mais de uma
responsabilidade, ela vira um **pacote** (uma pasta com `__init__.py`
reexportando o que é público), não um único arquivo gigante nem uma pilha
de arquivos soltos sem organização:

- `apps/core/models/` — um arquivo por model (`player.py`, `deck.py`,
  `card.py`, `game.py`, `game_participant.py`, `achievement.py`),
  reexportados em `models/__init__.py`.
- `apps/core/views/` — mesma ideia; hoje só tem `dashboard.py`, mas o
  padrão já está montado pra crescer sem virar um `views.py` de 500
  linhas.
- `apps/core/management/commands/` — um comando por arquivo, é o próprio
  formato que o Django exige.
- `requirements/` — `base.txt` (runtime) / `local.txt` (+ ferramentas de
  dev) / `production.txt`, espelhando o mesmo split de `config/settings/`.

Qualquer camada nova (a mais óbvia sendo a de use cases, descrita abaixo)
deve seguir o mesmo formato: um pacote com `__init__.py`, nunca um arquivo
único acumulando tudo.

## Dev-tool vs. prod-tool em `management/commands/`

Nem todo management command é seguro de rodar em qualquer lugar. O projeto
marca essa diferença explicitamente no código, não só na cabeça de quem
escreveu:

- [`import_mtgjson.py`](../apps/core/management/commands/import_mtgjson.py)
  é ferramenta de produção — baixa dados externos e só mexe na tabela
  `Card`, seguro em qualquer ambiente. A docstring da classe `Command`
  deixa isso explícito.
- [`seed_games.py`](../apps/core/management/commands/seed_games.py) é
  **dev-only e destrutivo** — apaga `Game`/`GameParticipant`/`Achievement`
  e gera dados aleatórios. Isso é reforçado de duas formas: a docstring +
  `help` (`"[DEV-ONLY] ..."`) avisam quem lê `manage.py help`, e um guard
  em `handle()` levanta `CommandError` se `settings.DEBUG` for `False` —
  ele fisicamente recusa rodar fora de um ambiente de desenvolvimento.

Ao criar um novo management command, pergunte: ele é seguro em produção?
Se não for, ele precisa da mesma dupla de sinalização (docstring/help +
guard de `DEBUG`).

## Camada de Use Cases (planejada, ainda não implementada)

A `DashboardView` hoje concentra toda a orquestração de regra de negócio
do dashboard direto em `get_context_data` (ver
[architecture.md](./architecture.md)). O plano é extrair isso pra uma
camada de use cases — **sem introduzir DDD, hexagonal ou uma abstração
pesada**, só uma camada fina de funções, seguindo a mesma convenção de
"pacote de arquivos" já usada em `models/` e `views/`:

- `apps/core/use_cases/` como pacote, um módulo por caso de uso — ex:
  `apps/core/use_cases/dashboard_stats.py` com uma função
  `get_dashboard_stats() -> dict` concentrando o que hoje está em
  `DashboardView.get_context_data` (ranking de jogadores, win rate,
  porcentagem de wincon, MVP).
- `apps/core/use_cases/__init__.py` reexportando as funções públicas, do
  mesmo jeito que `models/__init__.py` e `views/__init__.py` já fazem.
- Regra de ouro: depois que um use case existir pra uma tela, a view só
  chama a função e monta o `context` — nenhuma query/aggregate direto na
  view.

**Isso ainda não existe.** `DashboardView` continua com a lógica inline
até essa extração ser feita — este documento descreve a forma que ela deve
tomar quando acontecer, pra ninguém inventar uma estrutura diferente na
hora.

## Anti-objetivo explícito

Este projeto **não** usa DDD, Arquitetura Hexagonal ou uma camada de
serviços pesada. É um projeto pequeno — a meta é Django idiomático: models
gordos, views finas (via use cases quando a camada existir), funções e
classes simples em `management/commands/`. Se uma solução parece precisar
de mais de duas camadas de indireção pra um pod de 4 a 8 jogadores, é sinal
de over-engineering, não de arquitetura madura.
