#!/usr/bin/env bash
# Script de build do Render. Ver docs/superpowers/specs/ pro contexto do deploy.
set -o errexit

pip install -r requirements/production.txt

python manage.py collectstatic --noinput
python manage.py migrate

# Importa a base de cartas do MTGJSON só se o banco ainda estiver vazio —
# evita rebaixar e reprocessar ~35 mil cartas em todo deploy subsequente.
python manage.py shell -c "
from apps.core.models import Card
import sys
sys.exit(0 if Card.objects.exists() else 1)
" || python manage.py import_mtgjson
