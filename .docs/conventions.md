# Convenções de Organização

## Pacote de arquivos, não arquivo solto

Sempre que uma "camada" do projeto cresce o suficiente pra ter mais de uma
responsabilidade, ela vira um **pacote** (uma pasta com `__init__.py`
reexportando o que é público), não um único arquivo gigante nem uma pilha
de arquivos soltos sem organização:

- `apps/core/models/` — um arquivo por model (`player.py`, `deck.py`,
  `game.py`, `game_participant.py`, `achievement.py`), reexportados em
  `models/__init__.py`. `apps/pods/models/` (`pod.py`, `membership.py`)
  segue o mesmo padrão.
- `apps/core/views/`, `apps/core/forms/` — mesma ideia: um arquivo por
  view/form (`dashboard.py`, `game_create.py`, `deck_create.py`,
  `player_create.py`, ...), reexportados em `__init__.py`.
- `apps/core/management/commands/`, `apps/cards/management/commands/` —
  um comando por arquivo, é o próprio formato que o Django exige.
- `requirements/` — `base.txt` (runtime) / `local.txt` (+ ferramentas de
  dev) / `production.txt`, espelhando o mesmo split de `config/settings/`.

Esse padrão vale também no nível de **app**, não só de pacote dentro de
uma app: quando um conjunto de models/views passa a ter uma
responsabilidade claramente separada do resto (ex: catálogo de cartas
global vs. dado de um pod específico vs. identidade/multi-tenancy), ele
vira uma app nova (`apps/cards`, `apps/pods`, `apps/core`), não mais
código dentro da app que já existia. Ver `.docs/architecture.md` pra o
racional de cada divisão atual.

Qualquer camada nova (a mais óbvia sendo a de use cases, descrita abaixo)
deve seguir o mesmo formato: um pacote com `__init__.py`, nunca um arquivo
único acumulando tudo.

## Dev-tool vs. prod-tool em `management/commands/`

Nem todo management command é seguro de rodar em qualquer lugar. O projeto
marca essa diferença explicitamente no código, não só na cabeça de quem
escreveu:

- [`import_mtgjson.py`](../apps/cards/management/commands/import_mtgjson.py)
  é ferramenta de produção — baixa dados externos e só mexe na tabela
  `Card`, seguro em qualquer ambiente. A docstring da classe `Command`
  deixa isso explícito.
- [`seed_games.py`](../apps/core/management/commands/seed_games.py) é
  **dev-only e destrutivo** — recebe um `--pod <slug>` obrigatório, apaga
  `Game`/`GameParticipant`/`Achievement` **desse pod** e gera dados
  aleatórios pra ele. Isso é reforçado de duas formas: a docstring +
  `help` (`"[DEV-ONLY] ..."`) avisam quem lê `manage.py help`, e um guard
  em `handle()` levanta `CommandError` se `settings.DEBUG` for `False` —
  ele fisicamente recusa rodar fora de um ambiente de desenvolvimento.

Ao criar um novo management command, pergunte: ele é seguro em produção?
Se não for, ele precisa da mesma dupla de sinalização (docstring/help +
guard de `DEBUG`).

## Camada de Use Cases

Views não orquestram regra de negócio direto — isso vive numa camada de
use cases, **sem introduzir DDD, hexagonal ou uma abstração pesada**, só
uma camada fina de classes, seguindo a mesma convenção de "pacote de
arquivos" já usada em `models/` e `views/`:

- `apps/core/use_cases/` é um pacote, um módulo por caso de uso — ex:
  [`apps/core/use_cases/dashboard_stats.py`](../apps/core/use_cases/dashboard_stats.py)
  com a classe `DashboardStatsUseCase`, que concentra o que antes estava
  em `DashboardView.get_context_data` (ranking de jogadores, win rate,
  porcentagem de wincon, MVP).
- `apps/core/use_cases/__init__.py` reexporta as classes públicas, do
  mesmo jeito que `models/__init__.py` e `views/__init__.py` já fazem.
- Todo use case herda de
  [`apps.core.use_cases.base.BaseUseCase`](../apps/core/use_cases/base.py)
  (ver seção abaixo) e implementa `perform_request()`. Isso vale mesmo
  pra use cases de outras apps (`apps/pods/use_cases/`,
  `apps/cards/use_cases/`) — `BaseUseCase` é infra comum, não é regra de
  negócio de `core`.
- Regra de ouro: a view só instancia o use case e chama `.execute()` —
  nenhuma query/aggregate direto na view. CRUD simples (criar
  jogador/deck/partida) é exceção a essa regra — ver
  `.docs/architecture.md`, seção "Views são Class-Based e finas".

```python
class DashboardView(PodMemberRequiredMixin, TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(DashboardStatsUseCase().execute(self.pod))
        return context
```

Ao adicionar uma tela nova com lógica de agregação não trivial, siga esse
mesmo formato em vez de colocar a query direto em `get_context_data`.

## `BaseUseCase` — infraestrutura comum de logging

[`apps/core/use_cases/base.py`](../apps/core/use_cases/base.py) tem a
classe `BaseUseCase`, usada por toda use case do projeto (não só as de
`core`):

- `perform_request()` é abstrato (`@abstractmethod`) — toda subclasse é
  obrigada a implementar, senão nem instancia (`ABC` bloqueia isso em
  tempo de execução).
- `execute()` é o único método público. Ele loga início, sucesso/erro e
  fim, chama `perform_request()` dentro de um `try/except/finally`, e
  relança qualquer exceção depois de logar (`logger.exception`) — quem
  chama o use case decide o que fazer com o erro, o use case só garante
  que ele fica registrado.

Nenhum use case deve implementar sua própria lógica de logging/try-except
ao redor da chamada principal — isso é responsabilidade do `BaseUseCase`,
não de cada subclasse.

## Anti-objetivo explícito

Este projeto **não** usa DDD, Arquitetura Hexagonal ou uma camada de
serviços pesada. É um projeto pequeno — a meta é Django idiomático: models
gordos, views finas (via use cases), funções e classes simples em
`management/commands/`. Se uma solução parece precisar
de mais de duas camadas de indireção pra um pod de 4 a 8 jogadores, é sinal
de over-engineering, não de arquitetura madura.
