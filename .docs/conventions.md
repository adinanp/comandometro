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
  [`apps.shared.use_cases.BaseUseCase`](../apps/shared/use_cases/base.py)
  (ver seção abaixo) e implementa `perform_request()`.
- Regra de ouro: a view só instancia o use case e chama `.execute()` —
  nenhuma query/aggregate direto na view.

```python
class DashboardView(TemplateView):
    template_name = "core/dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(DashboardStatsUseCase().execute())
        return context
```

Ao adicionar uma tela nova com lógica de agregação não trivial, siga esse
mesmo formato em vez de colocar a query direto em `get_context_data`.

## Pacote `shared/` — código comum entre apps

`apps/shared/` existe pra código que qualquer app do projeto pode
precisar, sem pertencer à regra de negócio de nenhum app específico. Hoje
tem só uma coisa: `apps/shared/use_cases/base.py`, com a classe
`BaseUseCase`:

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
não de cada subclasse. Se `apps/shared/` crescer (outros mixins, base
classes, utilitários), ele segue a mesma regra de "pacote de arquivos":
uma pasta por concern, nunca um `utils.py` genérico acumulando tudo.

## Anti-objetivo explícito

Este projeto **não** usa DDD, Arquitetura Hexagonal ou uma camada de
serviços pesada. É um projeto pequeno — a meta é Django idiomático: models
gordos, views finas (via use cases), funções e classes simples em
`management/commands/`. Se uma solução parece precisar
de mais de duas camadas de indireção pra um pod de 4 a 8 jogadores, é sinal
de over-engineering, não de arquitetura madura.
