#!/usr/bin/env bash
# Deploy pro Google App Engine. O App Engine não tem etapa de build como o
# Render, então static, migrations e import de cartas rodam daqui, contra o
# banco de produção (Neon) definido no .env.production.
#
# Uso: scripts/deploy_gae.sh [--skip-migrate]
set -o errexit -o nounset -o pipefail

cd "$(dirname "$0")/.."

ENV_FILE=".env.production"
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Faltando $ENV_FILE (copie de .env.production.example)." >&2
  exit 1
fi

# Lido em Python, não com `source`: a URL do Neon tem "&", que o bash
# trataria como "rode em background". O Python grava o secrets.yaml (incluído
# pelo app.yaml) e devolve os exports já escapados pro shell. json.dumps gera
# strings que também são YAML válido.
exports="$(python - "$ENV_FILE" <<'PY'
import json, shlex, sys
from pathlib import Path

yaml_lines = ["env_variables:"]
for raw in Path(sys.argv[1]).read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    key, value = key.strip(), value.strip().strip('"').strip("'")
    print(f"export {key}={shlex.quote(value)}")
    if value:
        yaml_lines.append(f"  {key}: {json.dumps(value)}")
Path("secrets.yaml").write_text("\n".join(yaml_lines) + "\n")
PY
)"
eval "$exports"
export DJANGO_SETTINGS_MODULE=config.settings.production

python manage.py check --deploy
python manage.py collectstatic --noinput --clear

if [[ "${1:-}" != "--skip-migrate" ]]; then
  python manage.py migrate --noinput

  # Mesmo critério do build.sh: importa o catálogo só com o banco vazio.
  python manage.py shell -c "
from apps.cards.models import Card
import sys
sys.exit(0 if Card.objects.exists() else 1)
" || python manage.py import_mtgjson
fi

# O upload às vezes falha com erro 13 "Failed to copy file ... to Blobstore".
# Os arquivos já ficam no bucket de staging, então uma segunda tentativa
# passa. Só repete nesse caso: outras falhas param o script.
if ! gcloud app deploy app.yaml; then
  last_op="$(gcloud app operations list --limit=1 --sort-by=~startTime --format=json)"
  if grep -q "to Blobstore" <<<"$last_op"; then
    echo "Erro de cópia pro Blobstore, tentando o deploy de novo..." >&2
    gcloud app deploy app.yaml --quiet
  else
    exit 1
  fi
fi

# Cada deploy cria uma versão nova e a anterior continua de pé com 0% de
# tráfego, segurando a própria instância por causa do min_instances. Duas
# instâncias F1 estouram as 28h/dia grátis, então apaga as que sobraram.
old_versions="$(gcloud app versions list --service=default \
  --filter="traffic_split=0" --format="value(version.id)")"
if [[ -n "$old_versions" ]]; then
  # shellcheck disable=SC2086
  gcloud app versions delete --service=default --quiet $old_versions
fi
