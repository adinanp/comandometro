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

set -o allexport
# shellcheck disable=SC1090
source "$ENV_FILE"
set +o allexport
export DJANGO_SETTINGS_MODULE=config.settings.production

# secrets.yaml é incluído pelo app.yaml. json.dumps gera strings que também
# são YAML válido, então valores com ":" ou "#" não quebram o arquivo.
python - "$ENV_FILE" <<'PY'
import json, sys
from pathlib import Path

lines = ["env_variables:"]
for raw in Path(sys.argv[1]).read_text().splitlines():
    line = raw.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    value = value.strip().strip('"').strip("'")
    if value:
        lines.append(f"  {key.strip()}: {json.dumps(value)}")
Path("secrets.yaml").write_text("\n".join(lines) + "\n")
PY

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

gcloud app deploy app.yaml
