from .base import *  # noqa

DEBUG = False

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = True

# O Render termina TLS no proxy e encaminha pra gunicorn em HTTP puro — sem
# isso, request.is_secure() nunca é True e SECURE_SSL_REDIRECT vira loop
# infinito de redirect.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
