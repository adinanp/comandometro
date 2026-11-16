from .base import *  # noqa
from .base import DATABASES, env

DEBUG = False

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True

# O proxy (App Engine ou Render) termina TLS e encaminha pra gunicorn em HTTP
# puro — sem isso, request.is_secure() nunca é True e SECURE_SSL_REDIRECT
# vira loop infinito de redirect.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# O banco (Neon) fica fora da rede do app: abrir conexão TLS a cada request
# custa dezenas de ms. Reaproveita a conexão e testa antes de usar, porque o
# Neon free suspende o compute ocioso e derruba as conexões abertas.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("CONN_MAX_AGE", default=600)
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True

# O endpoint "-pooler" do Neon é PgBouncer em transaction mode, que não
# suporta server-side cursors (usados pelo .iterator()).
DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
