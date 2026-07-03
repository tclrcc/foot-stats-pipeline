#!/usr/bin/env bash
# Lance l'API de prédiction football.
#
# Dev (rechargement auto) :
#   ./run_api.sh
#
# Prod (sur le VPS, accessible depuis l'extérieur) :
#   ./run_api.sh prod
#
# Doc interactive : http://<host>:8000/docs

set -e
cd "$(dirname "$0")"

MODE="${1:-dev}"

if [ "$MODE" = "prod" ]; then
    echo "🚀 API en mode production (0.0.0.0:8000)"
    uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers 2
else
    echo "🔧 API en mode dev (rechargement auto)"
    uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000
fi
