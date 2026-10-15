#!/usr/bin/env bash
# ==============================================================================
# ArcIA — Déploiement Automatisé Universel sur Kubernetes (Bash / Linux / macOS)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
CONFIG_FILE="${1:-arcia.config.yaml}"

# Détection de l'interpréteur Python 3
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "ERREUR : Python 3 est requis mais n'a pas été trouvé dans le PATH."
    exit 1
fi

# Exécution du moteur universel de déploiement
exec "$PYTHON_BIN" "${SCRIPT_DIR}/deploy.py" --config "$CONFIG_FILE" "${@:2}"
