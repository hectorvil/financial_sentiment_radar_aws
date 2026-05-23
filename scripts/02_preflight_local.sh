#!/usr/bin/env bash
# Utility script for Financial Sentiment Radar.
#
# Run from the repository root after loading the environment variables
# required by the command being executed.
# Documented by Financial Sentiment Radar documentation patch.

set -euo pipefail

SKIP_DOCKER="${SKIP_DOCKER:-false}"
SKIP_AWS="${SKIP_AWS:-false}"

info() { printf '\n[INFO] %s\n' "$*"; }
pass() { printf '[PASS] %s\n' "$*"; }
fail() { printf '[FAIL] %s\n' "$*" >&2; exit 1; }
need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fail "Falta instalar '$1'."
}

info "Validando herramientas locales"
need_cmd git
need_cmd uv
need_cmd python3
need_cmd curl
pass "git, uv, python y curl disponibles"

if [[ "$SKIP_DOCKER" != "true" ]]; then
  need_cmd docker
  docker info >/dev/null 2>&1 || fail "Docker está instalado, pero el daemon no está corriendo. Abre Docker Desktop o inicia el servicio."
  pass "Docker disponible"
else
  info "Saltando validación de Docker por SKIP_DOCKER=true"
fi

if [[ "$SKIP_AWS" != "true" ]]; then
  need_cmd aws
  aws sts get-caller-identity >/dev/null || fail "AWS CLI no tiene credenciales válidas. Ejecuta 'aws configure' o exporta AWS_PROFILE."
  pass "AWS CLI autenticado"
else
  info "Saltando validación de AWS por SKIP_AWS=true"
fi

info "Validando estructura mínima del repositorio"
required_paths=(
  "README.md"
  "pyproject.toml"
  "Dockerfile"
  "app/streamlit_app.py"
  "src/financial_sentiment"
  "infra/cloudformation/00_foundation.yml"
  "infra/cloudformation/01_fargate_streamlit.yml"
  "scripts/00_deploy_foundation.sh"
  "scripts/06_build_push_app.sh"
  "scripts/07_deploy_ecs.sh"
  "data/sample_tweets.csv"
  "tests"
  "docs/product_definition.pdf"
  "docs/product_faq.pdf"
  "docs/architecture_solution.pdf"
  "docs/architecture_financial_sentiment_radar.drawio"
  "docs/presentacion_ejecutiva_15min.pptx"
)
for path in "${required_paths[@]}"; do
  [[ -e "$path" ]] || fail "No existe $path"
done
pass "Estructura mínima completa"

info "Validando que no haya secretos comunes en archivos versionables"
if find . \
  -path './.git' -prune -o \
  -path './.venv' -prune -o \
  -path './__pycache__' -prune -o \
  -type f \( -name '.env' -o -name '*.pem' -o -name '*.key' -o -name 'credentials' \) \
  -print | grep -q .; then
  find . \
    -path './.git' -prune -o \
    -path './.venv' -prune -o \
    -path './__pycache__' -prune -o \
    -type f \( -name '.env' -o -name '*.pem' -o -name '*.key' -o -name 'credentials' \) \
    -print
  fail "Hay archivos sensibles en el repo. Muévelos fuera o confirma que estén en .gitignore."
fi
pass "No se detectaron secretos por nombre de archivo"

info "Instalando/sincronizando dependencias de desarrollo con uv"
uv sync --all-groups
pass "Dependencias sincronizadas"

info "Ejecutando pruebas unitarias"
PYTHONPATH=src uv run pytest -q
pass "Tests OK"

info "Ejecutando lint con ruff"
uv run ruff check .
pass "Lint OK"

if [[ "$SKIP_AWS" != "true" ]]; then
  info "Validando templates de CloudFormation con AWS"
  aws cloudformation validate-template --template-body file://infra/cloudformation/00_foundation.yml >/dev/null
  aws cloudformation validate-template --template-body file://infra/cloudformation/01_fargate_streamlit.yml >/dev/null
  pass "CloudFormation templates OK"
fi

if [[ "$SKIP_DOCKER" != "true" ]]; then
  info "Construyendo imagen Docker local"
  docker build -t financial-sentiment-radar:preflight .
  pass "Docker build OK"
fi

info "Preflight finalizado correctamente"
