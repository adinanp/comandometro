# Boas Práticas e Convenções de Mercado

Convenções que passamos a seguir daqui pra frente — algumas corrigem
débitos que existiam no projeto, outras são só regras pra não regredir.

## Logging

Nunca usar `print()` pra diagnóstico ou depuração em código de produção.
Use `logging.getLogger(__name__)` no topo do módulo e logue nos pontos que
importam: início/fim de uma operação longa, contagens relevantes, e
sempre um `logger.exception(...)` antes de relançar um erro em código que
faz I/O externo (rede, arquivo, banco em lote).

[`import_mtgjson.py`](../apps/core/management/commands/import_mtgjson.py)
é a referência a seguir — ele loga o início do download, o total de
cartas encontradas, quantas foram criadas/atualizadas, e captura falhas de
rede com `logger.exception` antes de relançar.

`self.stdout.write(...)` em management commands continua existindo — é o
canal certo pra feedback de CLI pra quem está rodando o comando na mão.
Logging é complementar, não substitui isso.

A configuração de `LOGGING` vive em `config/settings/base.py`; o nível de
log é configurável via `.env` (`APP_LOG_LEVEL`, `DJANGO_LOG_LEVEL`) sem
precisar mexer em código.

## Segredos e settings

- Nunca hardcodar `SECRET_KEY`, senhas, tokens ou qualquer credencial
  direto num arquivo versionado — sempre via `env("...")`, lendo do
  `.env` (que já está no `.gitignore` e nunca deve ser commitado).
- Sempre que uma variável de ambiente nova for adicionada, atualizar o
  [`.env.example`](../.env.example) com o nome da variável (sem o valor
  real) — é a documentação viva de "o que preciso configurar pra rodar
  isso".
- Usar sempre o nome de setting que o Django realmente reconhece. O
  projeto tinha uma chave `MAILERS` que não é um setting válido do Django
  (o certo seria `EMAIL_BACKEND`) — foi removida por não estar em uso;
  é o exemplo do que evitar: configuração que parece fazer algo mas na
  prática é ignorada silenciosamente pelo framework.

## Segurança básica de produção

- `ALLOWED_HOSTS` deve vir de variável de ambiente
  (`env.list("ALLOWED_HOSTS", default=[])`), nunca hardcoded — uma lista
  vazia faz o Django recusar todo request com `DisallowedHost` assim que
  `DEBUG=False`.
- Em produção, cookies de sessão e CSRF devem exigir HTTPS
  (`SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`) e o `SECURE_SSL_REDIRECT`
  deve estar ligado — isso assume que o deploy real roda atrás de HTTPS.
  Em dev (`local.py`) isso fica desligado de propósito, porque o servidor
  local roda em HTTP puro.
- Rodar `manage.py check --deploy` antes de qualquer deploy real é uma boa
  prática barata — ele lista automaticamente settings de segurança que o
  Django recomenda e que ainda não estão configurados.
