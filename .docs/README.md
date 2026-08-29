# Comandometro — Documentação do Projeto

O Comandometro é uma aplicação Django multi-tenant para acompanhar as
partidas, decks e feitos de playgroups (pods) de Magic: The Gathering
(Commander/EDH) — cada usuário pode participar de vários pods, cada um
isolado dos outros. É um projeto pequeno e pessoal — a documentação abaixo
existe pra registrar as convenções que já usamos e evitar que o projeto
vire uma colcha de retalhos conforme cresce.

Esta pasta documenta **o que o projeto já faz** e **como queremos que ele
continue sendo construído**, não um design aspiracional distante da
realidade do código.

| Arquivo                                  | O que tem lá                                                                                                                                                                 |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| [architecture.md](./architecture.md)     | Os padrões já adotados no código: a divisão em apps (`cards`/`pods`/`core`), multi-tenancy por Pod, models com lógica de domínio, views baseadas em classe, login (allauth), settings/env/logging.                                           |
| [conventions.md](./conventions.md)       | Regras de organização de arquivos/pacotes, a diferença entre ferramentas de dev e de produção em `management/commands/`, e a camada de use cases. |
| [best-practices.md](./best-practices.md) | Convenções de mercado que adotamos daqui pra frente (logging, segredos, segurança básica de produção).                                                                      |

Regra geral: **este projeto não usa DDD, Hexagonal ou service-layer
pesado.** Ele segue as convenções idiomáticas do próprio Django — é pequeno
o suficiente pra isso ser suficiente.
